"""DynamoDB snapshots use mocked responses; no live AWS operations."""
import json
import os
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, ReadTimeoutError

import test_3a_cognito_auth as fixtures
from novamind.domain.session import _init_session_state, _clear_conversation
from services import auth_service as auth
from services import conversation_store as store
from services.authorization import AuthorizationError
from tests.offline_support import offline_guard


class MemoryDynamo:
    def __init__(self):
        self.items = {}
        self.writes = 0

    def get_item(self, **kwargs):
        key = kwargs["Key"]
        return {"Item": self.items.get((key["owner_key"]["S"], key["conversation_id"]["S"]))}

    def put_item(self, **kwargs):
        item = kwargs["Item"]
        key = (item["owner_key"]["S"], item["conversation_id"]["S"])
        existing = self.items.get(key)
        expected = kwargs.get("ExpressionAttributeValues", {}).get(":expected", {}).get("N")
        if (existing is not None and expected is None) or (
                expected is not None and (existing is None or existing["version"]["N"] != expected)):
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = item
        self.writes += 1

    def query(self, **kwargs):
        owner = kwargs["ExpressionAttributeValues"][":owner"]["S"]
        return {"Items": [item for (key_owner, _), item in self.items.items() if key_owner == owner]}


class TestDynamoPersistence(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_guard())
        self.enterContext(patch.dict(os.environ, {
            **fixtures.ENV, "NOVAMIND_DYNAMODB_TABLE": "novamind-conversations"}, clear=True))
        self.enterContext(patch.object(auth.time, "time", return_value=fixtures.NOW))
        self.cognito = Mock()
        tokens = {}
        def sign_in(**kwargs):
            name = kwargs["AuthParameters"]["USERNAME"]
            token = fixtures.token(username=name, sub="sub-" + name)
            tokens[token] = {"Username": name,
                             "UserAttributes": [{"Name": "sub", "Value": "sub-" + name}]}
            return {"AuthenticationResult": {"AccessToken": token}}
        self.cognito.initiate_auth.side_effect = sign_in
        self.cognito.get_user.side_effect = lambda **kwargs: tokens[kwargs["AccessToken"]]
        self.enterContext(patch.object(auth, "create_cognito_client", return_value=self.cognito))
        self.db = MemoryDynamo()
        self.alice = self.state("alice")
        self.bob = self.state("bob")

    def state(self, name):
        state = fixtures.State()
        auth.login(state, name, "mock-password")
        _init_session_state(state)
        return state

    def test_roundtrip_and_owner_scoped_keys(self):
        self.alice.chat_history.extend([
            {"role": "user", "text": "Private question", "thumbnail_bytes": b"secret"},
            {"role": "assistant", "text": "Private answer", "status": "completed"},
        ])
        self.alice.bedrock_history.extend([
            {"role": "user", "content": [{"text": "Private question"}]},
            {"role": "assistant", "content": [{"text": "Private answer"}]},
        ])
        old_id = self.alice.conversation_id
        self.assertEqual(store.save_conversation(self.alice, client=self.db), 1)
        item = next(iter(self.db.items.values()))
        self.assertNotIn("secret", item["payload"]["S"])
        self.assertNotIn("thumbnail_bytes", item["payload"]["S"])
        self.assertNotIn("sub-alice", str(item))
        _clear_conversation(self.alice)
        self.assertEqual(store.load_conversation(self.alice, old_id, client=self.db), 1)
        self.assertEqual(self.alice.chat_history[0]["text"], "Private question")
        self.assertEqual(self.alice.bedrock_history[1]["content"][0]["text"], "Private answer")
        self.assertEqual(self.alice.persistence_version, 1)

    def test_foreign_load_and_listing_are_isolated(self):
        store.save_conversation(self.alice, client=self.db)
        self.assertEqual(store.list_conversations(self.bob, client=self.db)["items"], [])
        with self.assertRaises(AuthorizationError):
            store.load_conversation(self.bob, self.alice.conversation_id, client=self.db)
        self.assertEqual(self.bob.chat_history, [])

    def test_version_conflict_blocks_stale_writer(self):
        store.save_conversation(self.alice, client=self.db)
        old_id = self.alice.conversation_id
        other = self.state("alice")
        store.load_conversation(other, old_id, client=self.db)
        self.alice.chat_history.append({"role": "user", "text": "first"})
        store.save_conversation(self.alice, client=self.db)
        other.chat_history.append({"role": "user", "text": "stale"})
        with self.assertRaises(store.VersionConflict):
            store.save_conversation(other, client=self.db)
        self.assertNotIn("stale", next(iter(self.db.items.values()))["payload"]["S"])

    def test_retry_same_request_does_not_write_twice(self):
        request_id = "a" * 32
        self.db.put_item = Mock(wraps=self.db.put_item)
        store.save_conversation(self.alice, client=self.db, request_id=request_id)
        # Simulate a lost response: local version was never advanced.
        from services.authorization import publish_data
        publish_data(self.alice, persistence_version=0)
        self.assertEqual(store.save_conversation(self.alice, client=self.db,
                                                 request_id=request_id), 1)
        self.assertEqual(self.db.writes, 1)
        publish_data(self.alice, persistence_version=0)
        self.alice.chat_history.append({"role": "user", "text": "changed payload"})
        with self.assertRaises(store.VersionConflict):
            store.save_conversation(self.alice, client=self.db, request_id=request_id)

    def test_ambiguous_write_timeout_is_confirmed_without_repeating_put(self):
        put_once = self.db.put_item

        def commit_then_timeout(**kwargs):
            put_once(**kwargs)
            raise ReadTimeoutError(endpoint_url="https://dynamodb.invalid")

        self.db.put_item = Mock(side_effect=commit_then_timeout)
        with patch("services.aws_retries.time.sleep"):
            self.assertEqual(store.save_conversation(self.alice, client=self.db), 1)
        self.db.put_item.assert_called_once()
        self.assertEqual(self.db.writes, 1)
        self.assertEqual(self.alice.persistence_version, 1)

    def test_bounded_history_and_no_binary_context(self):
        for index in range(50):
            self.alice.chat_history.append({"role": "user", "text": str(index)})
        self.alice.bedrock_history.extend([
            {"role": "user", "content": [{"image": {"source": {"bytes": b"private"}}}]},
            {"role": "assistant", "content": [{"text": "image response"}]},
            {"role": "user", "content": [{"text": "safe"}]},
            {"role": "assistant", "content": [{"text": "reply"}]},
        ])
        store.save_conversation(self.alice, client=self.db)
        payload = json.loads(next(iter(self.db.items.values()))["payload"]["S"])
        self.assertEqual(len(payload["chat_history"]), store.MAX_MESSAGES)
        self.assertEqual(len(payload["bedrock_history"]), 2)
        self.assertNotIn("private", str(payload))

    def test_invalid_table_and_id_fail_before_database_access(self):
        with self.assertRaises(AuthorizationError):
            store.load_conversation(self.alice, "../foreign", client=self.db)
        with patch.dict(os.environ, {"NOVAMIND_DYNAMODB_TABLE": "bad/table"}):
            with self.assertRaises(store.PersistenceError):
                store.save_conversation(self.alice, client=self.db)
        self.assertEqual(self.db.writes, 0)
