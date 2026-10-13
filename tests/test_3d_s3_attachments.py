"""Focused offline S3/Dynamo integration; no real clients or network."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from botocore.exceptions import ReadTimeoutError

import test_3c_dynamodb_persistence as fixtures
from services import attachment_store as attachments, conversation_store as store
from services.authorization import AuthorizationError, capture_scope


class TestPrivateAttachments(unittest.TestCase):
    setUp = fixtures.TestDynamoPersistence.setUp
    state = fixtures.TestDynamoPersistence.state

    def setup_storage(self):
        self.enterContext(patch.dict(os.environ, {"NOVAMIND_S3_BUCKET": "novamind-private"}))
        self.s3 = Mock()
        self.objects = {}
        self.s3.put_object.side_effect = lambda **kw: self.objects.update({kw["Key"]: kw["Body"]})
        self.s3.get_object.side_effect = lambda **kw: {
            "Body": io.BytesIO(self.objects[kw["Key"]]),
            "ContentLength": len(self.objects[kw["Key"]])}
        self.alice.bedrock_history.extend([
            {"role": "user", "content": [{"text": "read"}, {"document": {
                "format": "txt", "name": "private", "source": {"bytes": b"private content"}}}]},
            {"role": "assistant", "content": [{"text": "answer"}]},
        ])

    def save(self):
        return store.save_conversation(self.alice, client=self.db, s3_client=self.s3)

    def test_roundtrip_private_encrypted_and_no_bytes_in_dynamo(self):
        self.setup_storage()
        self.save()
        payload = next(iter(self.db.items.values()))["payload"]["S"]
        self.assertNotIn("private content", payload)
        self.assertEqual(self.s3.put_object.call_args.kwargs["ServerSideEncryption"], "AES256")
        self.assertNotIn("ACL", self.s3.put_object.call_args.kwargs)
        store.load_conversation(self.alice, self.alice.conversation_id, client=self.db, s3_client=self.s3)
        self.assertEqual(self.alice.bedrock_history[0]["content"][1]["document"]["source"]["bytes"], b"private content")

    def test_timeout_while_reading_object_retries_and_closes_each_body(self):
        self.setup_storage()
        self.save()

        class FailingBody(io.BytesIO):
            def read(self, size=-1):
                raise ReadTimeoutError(endpoint_url="https://s3.invalid")

        timeout_body = FailingBody()
        calls = 0

        def get_object(**kwargs):
            nonlocal calls
            calls += 1
            body = timeout_body if calls == 1 else io.BytesIO(self.objects[kwargs["Key"]])
            return {"Body": body, "ContentLength": len(self.objects[kwargs["Key"]])}

        self.s3.get_object.side_effect = get_object
        with patch("services.aws_retries.time.sleep"):
            store.load_conversation(self.alice, self.alice.conversation_id,
                                    client=self.db, s3_client=self.s3)
        self.assertEqual(calls, 2)
        self.assertTrue(timeout_body.closed)

    def test_foreign_user_cannot_fetch(self):
        self.setup_storage()
        self.save()
        with self.assertRaises(AuthorizationError):
            store.load_conversation(self.bob, self.alice.conversation_id, client=self.db, s3_client=self.s3)
        self.s3.get_object.assert_not_called()

    def test_foreign_key_and_expiration_fail_before_get(self):
        self.setup_storage()
        self.save()
        item = next(iter(self.db.items.values()))
        original = item["payload"]["S"]
        for field, value in (("key", "attachments/foreign/secret"), ("expires_at", 0), ("size", 99_000_000)):
            data = json.loads(original)
            data["bedrock_history"][0]["content"][1]["document"]["attachment"][field] = value
            item["payload"]["S"] = json.dumps(data)
            with self.assertRaises(store.PersistenceError):
                store.load_conversation(self.alice, self.alice.conversation_id, client=self.db, s3_client=self.s3)
        self.s3.get_object.assert_not_called()

    def test_corruption_rejected_without_publishing(self):
        self.setup_storage()
        self.save()
        history = self.alice.bedrock_history
        key = next(iter(self.objects))
        self.objects[key] = b"corrupt content"
        with self.assertRaises(store.PersistenceError):
            store.load_conversation(self.alice, self.alice.conversation_id, client=self.db, s3_client=self.s3)
        self.assertIs(self.alice.bedrock_history, history)

    def test_oversize_rejected_before_upload(self):
        self.setup_storage()
        self.alice.bedrock_history[0]["content"][1]["document"]["source"]["bytes"] = b"x" * 5_000_000
        with self.assertRaises(store.PersistenceError):
            self.save()
        self.s3.put_object.assert_not_called()
        self.assertEqual(self.db.writes, 0)

    def test_cleanup_scoped_and_retryable(self):
        self.setup_storage()
        self.save()
        item = next(iter(self.db.items.values()))
        def update(**kw):
            item["deleted"] = {"BOOL": True}
        self.db.update_item = Mock(side_effect=update)
        self.s3.list_objects_v2.side_effect = [{"Contents": [{"Key": next(iter(self.objects))}]}, {}]
        store.delete_conversation(self.alice, self.alice.conversation_id, client=self.db, s3_client=self.s3)
        self.s3.delete_object.assert_called_once()
        self.assertEqual(self.db.update_item.call_count, 2)
        with self.assertRaises(AuthorizationError):
            store.load_conversation(self.alice, self.alice.conversation_id, client=self.db, s3_client=self.s3)

    def test_stale_scope_blocks_upload(self):
        self.setup_storage()
        scope = capture_scope(self.alice)
        from novamind.domain.session import _clear_conversation
        _clear_conversation(self.alice)
        with self.assertRaises(AuthorizationError):
            attachments.freeze(self.alice, scope, "a" * 64, [{"role": "user", "content": [
                {"document": {"format": "txt", "source": {"bytes": b"safe text"}}}]}], client=self.s3)
        self.s3.put_object.assert_not_called()

    def test_cleanup_failure_keeps_tombstone_for_retry(self):
        from botocore.exceptions import ClientError
        self.setup_storage()
        self.save()
        item = next(iter(self.db.items.values()))
        self.db.update_item = Mock(side_effect=lambda **kw: item.update(deleted={"BOOL": True}))
        self.s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "sensitive"}}, "ListObjectsV2")
        with self.assertRaises(store.PersistenceError) as error:
            store.delete_conversation(self.alice, self.alice.conversation_id, client=self.db, s3_client=self.s3)
        self.assertNotIn("sensitive", str(error.exception))
        self.assertEqual(self.db.update_item.call_count, 1)
        self.assertIn("payload", item)
        self.assertTrue(store.list_conversations(self.alice, client=self.db)["items"])

    def test_upload_failure_never_commits_dynamo(self):
        from botocore.exceptions import ClientError
        self.setup_storage()
        self.s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "PutObject")
        with self.assertRaises(store.PersistenceError):
            self.save()
        self.assertEqual(self.db.writes, 0)
