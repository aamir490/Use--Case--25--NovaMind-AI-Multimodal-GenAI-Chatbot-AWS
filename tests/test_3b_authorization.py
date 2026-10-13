"""Ownership and stale-operation regressions; every AWS boundary stays mocked."""
import io
import os
import unittest
from unittest.mock import Mock, MagicMock, patch

import test_3a_cognito_auth as auth_fixtures
import test_1e_stream_integrity as stream_fixtures
from tests.offline_support import offline_environment, offline_guard
from services import auth_service as auth
from services import authorization as access
from services.bedrock_service import BedrockService
from services.document_service import DocumentResult
from novamind.domain import session, usage
from novamind.orchestration import uploads, bedrock


class Upload(io.BytesIO):
    name = "notes.txt"
    file_id = "browser-controlled-id"


class TestAuthorization(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_guard())
        self.enterContext(patch.dict(os.environ, auth_fixtures.ENV, clear=True))
        self.enterContext(patch.object(auth.time, "time", return_value=auth_fixtures.NOW))
        self.cognito = Mock()
        self.tokens = {}
        def sign_in(**kwargs):
            username = kwargs["AuthParameters"]["USERNAME"]
            token = auth_fixtures.token(username=username, sub="sub-" + username)
            self.tokens[token] = {"Username": username,
                                  "UserAttributes": [{"Name": "sub", "Value": "sub-" + username}]}
            return {"AuthenticationResult": {"AccessToken": token}}
        self.cognito.initiate_auth.side_effect = sign_in
        self.cognito.get_user.side_effect = lambda **kw: self.tokens[kw["AccessToken"]]
        self.enterContext(patch.object(auth, "create_cognito_client", return_value=self.cognito))
        self.alice = self.new_state("alice")
        self.bob = self.new_state("bob")
        self.alice.chat_history.append({"role": "user", "text": "ALICE_PRIVATE"})
        self.bob.chat_history.append({"role": "user", "text": "BOB_PRIVATE"})

    def new_state(self, username):
        state = auth_fixtures.State()
        auth.login(state, username, "mock-password")
        session._init_session_state(state)
        return state

    def upload(self, state, content=b"private attachment"):
        doc = DocumentResult("notes.txt", len(content), "txt", content, content.decode())
        with patch.object(uploads, "validate_file_upload", return_value=doc):
            uploads._handle_file_upload(state, Upload(content))
        return state.attachment_id

    def service(self, state, client=None):
        client = client or Mock()
        with patch("services.bedrock_service.create_aws_client", return_value=client):
            service = BedrockService(auth_session=state.auth_session)
        access.publish_data(state, bedrock_service=service)
        return service, client

    def test_principal_comes_from_verified_identity_not_display_or_client_ids(self):
        self.alice.update(login_user="bob", user_id="sub-bob", owner_id="sub-bob", username="bob")
        scope = access.capture_scope(self.alice)
        self.assertEqual(scope.principal, ("cognito", auth.load_auth_config().issuer, "sub-alice"))
        self.assertIn("ALICE_PRIVATE", access.export_conversation(self.alice))
        self.assertNotIn("BOB_PRIVATE", access.export_conversation(self.alice))
        with self.assertRaises(access.AuthorizationError):
            access.conversation_snapshot(self.alice, self.bob.conversation_id)

    def test_foreign_unknown_and_path_like_ids_all_deny_read_write_delete_export(self):
        foreign_scope = access.capture_scope(self.bob)
        for resource_id in (self.bob.conversation_id, "missing", "../bob", "sub-bob"):
            for action in (access.conversation_snapshot, access.export_conversation, session._clear_conversation):
                with self.subTest(resource_id=resource_id, action=action):
                    with self.assertRaisesRegex(access.AuthorizationError, "not available"):
                        action(self.alice, resource_id)
            with self.assertRaises(access.AuthorizationError):
                access.publish_data(self.alice, expected=foreign_scope, chat_history=[])
        self.assertEqual(self.alice.chat_history[0]["text"], "ALICE_PRIVATE")
        self.assertEqual(self.bob.chat_history[0]["text"], "BOB_PRIVATE")

    def test_state_owner_relabelling_does_not_grant_access(self):
        self.alice["data_owner"] = "sub-bob"
        with self.assertRaises(auth.AuthenticationError):
            access.export_conversation(self.alice)
        self.assertEqual(self.alice, {})
        self.assertIn("BOB_PRIVATE", access.export_conversation(self.bob))

    def test_conversation_id_tampering_cannot_adopt_a_foreign_conversation(self):
        self.alice["conversation_id"] = self.bob.conversation_id
        with self.assertRaises(access.AuthorizationError):
            session._clear_conversation(self.alice)
        self.assertIn("BOB_PRIVATE", access.export_conversation(self.bob))

    def test_replacing_verified_subject_and_token_does_not_reassign_existing_data(self):
        self.alice.auth_session.subject = self.bob.auth_session.subject
        self.alice.auth_session.username = self.bob.auth_session.username
        self.alice.auth_session.token = self.bob.auth_session.token
        self.alice["data_owner"] = self.bob.data_owner
        with self.assertRaises(access.AuthorizationError):
            access.export_conversation(self.alice)
        self.assertIn("BOB_PRIVATE", access.export_conversation(self.bob))

    def test_transplanted_history_ledger_and_attachments_are_rejected(self):
        self.upload(self.bob)
        for field in ("chat_history", "bedrock_history", "usage_ledger", "pending_document"):
            state = self.new_state("alice")
            state[field] = self.bob[field]
            with self.subTest(field=field), self.assertRaises(access.AuthorizationError):
                auth.protect_state(state)
            self.assertEqual(state, {})
            self.assertIn("BOB_PRIVATE", access.export_conversation(self.bob))
        self.assertEqual(self.bob.pending_document.raw_bytes, b"private attachment")

    def test_unregistered_content_and_deleted_owned_field_fail_closed(self):
        del self.alice["usage_ledger"]
        with self.assertRaises(access.AuthorizationError):
            usage._record_usage(self.alice, [], "completed", "chat")
        self.assertEqual(self.alice, {})
        state = auth_fixtures.State()
        auth.login(state, "alice", "password")
        state["chat_history"] = self.bob.chat_history
        with self.assertRaises(access.AuthorizationError):
            session._init_session_state(state)

    def test_snapshots_are_detached_and_own_export_preserves_text(self):
        copied = access.conversation_snapshot(self.alice, self.alice.conversation_id)
        copied[0]["text"] = "modified"
        copied.append({"role": "assistant", "text": "injected"})
        self.assertEqual(len(self.alice.chat_history), 1)
        self.assertIn("ALICE_PRIVATE", access.export_conversation(self.alice, self.alice.conversation_id))

    def test_same_user_separate_logins_remain_separate_resources(self):
        second = self.new_state("alice")
        self.assertEqual(second.auth_session.subject, self.alice.auth_session.subject)
        self.assertNotEqual(second.conversation_id, self.alice.conversation_id)
        with self.assertRaises(access.AuthorizationError):
            access.export_conversation(second, self.alice.conversation_id)
        self.assertEqual(second.chat_history, [])

    def test_new_chat_invalidates_previous_id_and_inflight_write_scope(self):
        previous = access.capture_scope(self.alice)
        session._clear_conversation(self.alice, previous.conversation_id)
        self.assertNotEqual(self.alice.conversation_id, previous.conversation_id)
        with self.assertRaises(access.AuthorizationError):
            access.export_conversation(self.alice, previous.conversation_id)
        with self.assertRaises(access.AuthorizationError):
            access.publish_data(self.alice, expected=previous, chat_history=[{"text": "late"}])
        self.assertEqual(self.alice.chat_history, [])

    def test_attachment_ids_are_server_created_and_scoped(self):
        alice_id = self.upload(self.alice, b"ALICE_ATTACHMENT")
        bob_id = self.upload(self.bob, b"BOB_ATTACHMENT")
        self.assertNotEqual(alice_id, bob_id)
        self.assertNotEqual(alice_id, Upload.file_id)
        for requested in (bob_id, Upload.file_id, "notes.txt", "../bob", "missing"):
            with self.subTest(requested=requested):
                with self.assertRaises(access.AuthorizationError):
                    access.attachment_snapshot(self.alice, requested)
                with self.assertRaises(access.AuthorizationError):
                    session._reset_attachment(self.alice, requested)
        copied = access.attachment_snapshot(self.alice, alice_id)
        copied.raw_bytes = b"modified"
        self.assertEqual(self.alice.pending_document.raw_bytes, b"ALICE_ATTACHMENT")
        session._reset_attachment(self.alice, alice_id)
        with self.assertRaises(access.AuthorizationError):
            access.attachment_snapshot(self.alice, alice_id)
        self.assertEqual(access.attachment_snapshot(self.bob, bob_id).raw_bytes, b"BOB_ATTACHMENT")

    def test_attachment_replacement_revokes_old_resource_id(self):
        old_id = self.upload(self.alice, b"old")
        # A fresh browser selection has a different cache hint, not a new owner.
        with patch.object(Upload, "file_id", "new-selection"):
            new_id = self.upload(self.alice, b"new")
        self.assertNotEqual(old_id, new_id)
        with self.assertRaises(access.AuthorizationError):
            access.attachment_snapshot(self.alice, old_id)

    def test_stale_widget_from_previous_login_cannot_upload_to_new_user(self):
        key = session._upload_widget_key(self.alice)
        auth.login(self.alice, "bob", "password")
        session._init_session_state(self.alice)
        self.assertNotEqual(session._upload_widget_key(self.alice), key)
        self.alice[key] = Upload(b"old-user")
        with patch.object(uploads, "validate_file_upload") as parse:
            uploads._on_upload_changed(self.alice, key)
        parse.assert_not_called()
        self.assertIsNone(self.alice.pending_document)

    def test_upload_finishing_after_new_chat_cannot_publish_result(self):
        doc = DocumentResult("notes.txt", 3, "txt", b"old", "old")
        def parse(*args):
            session._clear_conversation(self.alice)
            return doc
        with patch.object(uploads, "validate_file_upload", side_effect=parse):
            with self.assertRaises(access.AuthorizationError):
                uploads._handle_file_upload(self.alice, Upload(b"old"))
        self.assertIsNone(self.alice.pending_document)
        self.assertIsNone(self.alice.attachment_id)
        auth.protect_state(self.alice)

    def test_upload_failure_after_account_switch_cannot_write_error_into_new_session(self):
        def parse(*args):
            auth.login(self.alice, "bob", "password")
            session._init_session_state(self.alice)
            raise ValueError("old-user parser detail")
        with patch.object(uploads, "validate_file_upload", side_effect=parse):
            with self.assertRaises(access.AuthorizationError):
                uploads._handle_file_upload(self.alice, Upload(b"old"))
        self.assertEqual(self.alice.auth_session.subject, "sub-bob")
        self.assertIsNone(self.alice.upload_error)
        self.assertIsNone(self.alice.pending_document)

    def test_foreign_cached_service_rejected_without_closing_victims_client(self):
        service, client = self.service(self.bob)
        self.alice["bedrock_service"] = service
        with self.assertRaises(access.AuthorizationError):
            bedrock._get_or_create_service(self.alice)
        client.close.assert_not_called()
        client.converse_stream.assert_not_called()
        self.assertTrue(self.bob.auth_session.active)
        self.assertIs(bedrock._get_or_create_service(self.bob), service)

    def test_publishing_foreign_cached_service_is_rejected(self):
        service, client = self.service(self.bob)
        with self.assertRaises(access.AuthorizationError):
            access.publish_data(self.alice, bedrock_service=service)
        self.assertIsNone(self.alice.bedrock_service)
        client.close.assert_not_called()

    def test_service_creation_finishing_after_new_chat_closes_new_client(self):
        service = Mock(_auth_session=self.alice.auth_session)
        def create(**kwargs):
            session._clear_conversation(self.alice)
            return service
        with patch.object(bedrock, "get_bedrock_service", side_effect=create):
            with self.assertRaises(access.AuthorizationError):
                bedrock._get_or_create_service(self.alice)
        self.assertIsNone(self.alice.bedrock_service)
        service._client.close.assert_called_once()

    def test_stale_stream_stops_before_output_or_history_commit(self):
        scope = access.capture_scope(self.alice)
        service, client = self.service(self.alice)
        stream = stream_fixtures.FakeStream([stream_fixtures.delta("private"), stream_fixtures.stop()])
        def response(**kwargs):
            session._clear_conversation(self.alice)
            return {"stream": stream}
        client.converse_stream.side_effect = response
        history = []
        with self.assertRaises(access.AuthorizationError):
            list(service.stream_response("q", history,
                 authorization_check=lambda: access.check_scope(self.alice, scope)))
        self.assertEqual(history, [])
        self.assertEqual(self.alice.chat_history, [])
        self.assertEqual(stream.closed, 1)

    def test_ui_rejects_foreign_history_service_and_attachment_before_calling_bedrock(self):
        from novamind.ui import chat
        st = MagicMock()
        st.session_state = self.alice
        service, client = self.service(self.bob)
        self.upload(self.bob)
        with patch.object(chat, "st", st):
            with self.assertRaises(access.AuthorizationError):
                chat._stream_and_display_response("q", service, None, None)
            with self.assertRaises(access.AuthorizationError):
                chat._stream_and_display_response("q", None, None, None, history=self.bob.bedrock_history)
            with self.assertRaises(access.AuthorizationError):
                chat._stream_and_display_response("q", None, None, self.bob.pending_document,
                                                  attachment_selection=access.capture_attachments(self.bob))
        client.converse_stream.assert_not_called()

    def test_conversation_switch_during_online_verification_prevents_invocation(self):
        scope = access.capture_scope(self.alice)
        service, client = self.service(self.alice)
        checks = 0
        def verify(*args, **kwargs):
            nonlocal checks
            auth.authorize_bedrock(*args, **kwargs)
            checks += 1
            if checks == 2:
                session._clear_conversation(self.alice)
        with patch("services.bedrock_service.authorize_bedrock", side_effect=verify):
            with self.assertRaises(access.AuthorizationError):
                service.invoke_response("q", [],
                    authorization_check=lambda: access.check_scope(self.alice, scope))
        client.converse_stream.assert_not_called()

    def test_conversation_switch_during_stream_cleanup_prevents_history_commit(self):
        scope = access.capture_scope(self.alice)
        service, client = self.service(self.alice)
        stream = stream_fixtures.FakeStream([stream_fixtures.delta("old answer"), stream_fixtures.stop()])
        close = stream.close
        def close_and_switch():
            close()
            session._clear_conversation(self.alice)
        stream.close = close_and_switch
        client.converse_stream.return_value = {"stream": stream}
        history = []
        with self.assertRaises(access.AuthorizationError):
            service.invoke_response("q", history,
                authorization_check=lambda: access.check_scope(self.alice, scope))
        self.assertEqual(history, [])
        self.assertEqual(stream.closed, 1)

    def test_live_diagnostic_rejects_stale_scope_and_closes_client(self):
        service, client = self.service(self.alice)
        def response(**kwargs):
            session._clear_conversation(self.alice)
            return {"stream": stream_fixtures.FakeStream([stream_fixtures.delta("OK"), stream_fixtures.stop()])}
        client.converse_stream.side_effect = response
        with patch.object(bedrock, "get_bedrock_service", return_value=service):
            with self.assertRaises(access.AuthorizationError):
                bedrock._check_aws_connection(self.alice, live=True)
        client.close.assert_called_once()
        self.assertIsNone(self.alice.aws_status)

    def test_stale_stream_failure_does_not_render_previous_users_text(self):
        from novamind.ui import chat
        st = MagicMock()
        st.session_state = self.alice
        service, client = self.service(self.alice)
        def events():
            yield stream_fixtures.delta("old private text")
            auth.login(self.alice, "bob", "password")
            session._init_session_state(self.alice)
            st.empty.return_value.markdown.reset_mock()
            raise RuntimeError("stream failed after switch")
        client.converse_stream.return_value = {"stream": stream_fixtures.FakeStream(events())}
        with patch.object(chat, "st", st), patch.object(chat, "_record_usage") as record:
            with self.assertRaises(access.AuthorizationError):
                chat._stream_and_display_response("q", service, None, None)
        st.empty.return_value.markdown.assert_not_called()
        record.assert_not_called()
        self.assertEqual(self.alice.auth_session.subject, "sub-bob")
        self.assertEqual(self.alice.chat_history, [])

    def test_ui_does_not_account_or_commit_a_result_into_a_new_conversation(self):
        from novamind.ui import chat
        st = MagicMock()
        st.session_state = self.alice
        service, client = self.service(self.alice)
        def response(**kwargs):
            session._clear_conversation(self.alice)
            return {"stream": stream_fixtures.FakeStream([stream_fixtures.delta("late"), stream_fixtures.stop()])}
        client.converse_stream.side_effect = response
        with patch.object(chat, "st", st), patch.object(chat, "_record_usage") as record:
            with self.assertRaises(access.AuthorizationError):
                chat._stream_and_display_response("q", service, None, None)
        record.assert_not_called()
        self.assertEqual(self.alice.usage_ledger, [])
        self.assertEqual(self.alice.bedrock_history, [])

    def test_unauthenticated_expired_and_logged_out_data_access_fails(self):
        for state in (auth_fixtures.State(logged_in=True, login_user="alice"), self.alice):
            if state is self.alice:
                auth.logout(state)
            with self.assertRaises(auth.AuthenticationError):
                access.export_conversation(state)
        self.bob.auth_session.expires_at = auth_fixtures.NOW
        with self.assertRaises(auth.AuthenticationError):
            access.conversation_snapshot(self.bob)


class TestLocalDemoAuthorization(unittest.TestCase):
    def test_demo_accounts_and_tabs_are_isolated_without_cognito(self):
        with offline_environment(), offline_guard(), patch.object(auth, "create_cognito_client") as client:
            states = []
            for username, password in (("demo", "demo1234"), ("admin", "novabot123"), ("demo", "demo1234")):
                state = auth_fixtures.State()
                auth.login(state, username, password)
                session._init_session_state(state)
                states.append(state)
            states[0].chat_history.append({"role": "user", "text": "private demo"})
            for other in states[1:]:
                with self.assertRaises(access.AuthorizationError):
                    access.export_conversation(other, states[0].conversation_id)
                self.assertEqual(other.chat_history, [])
            self.assertEqual(len({state.conversation_id for state in states}), 3)
            client.assert_not_called()
