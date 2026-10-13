"""Offline memory selection, stream rollback, scope rotation and restore tests."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock

import test_1e_stream_integrity as streams
import test_3c_dynamodb_persistence as persistence
from services.conversation_memory import request_history, single_turn
from services.request_limits import RequestLimitError
from services.authorization import capture_scope, check_scope, AuthorizationError
from services import conversation_store as store
from novamind.domain.session import _clear_conversation
from tests.frontend_support import load_frontend


def pair(text):
    return [{"role": "user", "content": [{"text": text}]},
            {"role": "assistant", "content": [{"text": "answer"}]}]


class TestBoundedMemory(streams.OfflineCase):
    def test_recent_complete_pairs_bounded_without_mutating_source(self):
        history = sum((pair(str(i)) for i in range(30)), [])
        before = deepcopy(history)
        selected = request_history(self.service, history, [{"text": "follow up"}])
        self.assertEqual(len(selected), 38)
        self.assertEqual(selected[0]["content"][0]["text"], "11")
        self.assertEqual(history, before)

    def test_budget_evicts_old_pairs_and_preserves_recent_attachment(self):
        history = pair("x" * 125000) + pair("recent")
        history[-2]["content"].insert(0, {"image": {
            "format": "png", "source": {"bytes": b"image"}}})
        selected = request_history(self.service, history, [{"text": "what was in it?"}])
        self.assertEqual(selected, history[-2:])
        self.assertEqual(selected[0]["content"][0]["image"]["source"]["bytes"], b"image")

    def test_new_input_cannot_be_trimmed_away(self):
        history = pair("recent")
        with self.assertRaises(RequestLimitError):
            request_history(self.service, history, [{"text": "x" * 128000}])
        self.assertEqual(history, pair("recent"))

    def test_invalid_old_attachment_is_not_silently_evicted(self):
        history = pair("old") + pair("recent")
        history[0]["content"].insert(0, {"image": {"format": "bad", "source": {"bytes": b"x"}}})
        with self.assertRaises(RequestLimitError):
            request_history(self.service, history, [{"text": "question"}])

    def test_ui_success_commits_bounded_pairs_failure_rolls_back(self):
        st = MagicMock()
        st.session_state = streams.SessionState()
        ui = load_frontend(st, self)
        ui._init_session_state()
        ui._get_or_create_service = lambda: self.service
        st.session_state.bedrock_history[:] = sum((pair(str(i)) for i in range(25)), [])
        before = deepcopy(st.session_state.bedrock_history)
        self.respond([streams.delta("partial")])
        ui._handle_user_input("follow up")
        self.assertEqual(st.session_state.bedrock_history, before)
        self.respond([streams.delta("complete"), streams.stop()])
        ui._handle_user_input("follow up")
        self.assertEqual(len(st.session_state.bedrock_history), 40)
        self.assertEqual(st.session_state.bedrock_history[-2]["content"], [{"text": "follow up"}])


class TestRestoredMemory(unittest.TestCase):
    setUp = persistence.TestDynamoPersistence.setUp
    state = persistence.TestDynamoPersistence.state

    def test_restore_settings_and_followup_context_replace_other_chat(self):
        self.alice.system_prompt = "Saved persona"
        self.alice.temperature = 0.2
        self.alice.max_tokens = 512
        self.alice.bedrock_history.extend(pair("remember my preference"))
        store.save_conversation(self.alice, client=self.db)
        saved_id = self.alice.conversation_id
        old_scope = capture_scope(self.alice)
        _clear_conversation(self.alice)
        self.alice.system_prompt = "Other persona"
        self.alice.bedrock_history.extend(pair("other chat secret"))
        store.load_conversation(self.alice, saved_id, client=self.db)
        self.assertEqual(self.alice.system_prompt, "Saved persona")
        self.assertEqual((self.alice.temperature, self.alice.max_tokens), (0.2, 512))
        self.assertEqual(self.alice.bedrock_history, pair("remember my preference"))
        with self.assertRaises(AuthorizationError):
            check_scope(self.alice, old_scope)
        self.assertEqual(self.bob.bedrock_history, [])
        from services.bedrock_service import BedrockService
        from unittest.mock import Mock, patch
        client = Mock()
        client.converse_stream.return_value = {"stream": streams.FakeStream([
            streams.delta("remembered"), streams.stop()])}
        with patch("services.bedrock_service.create_aws_client", return_value=client):
            service = BedrockService(auth_session=self.alice.auth_session,
                                     model_id="amazon.nova-pro-v1:0", region="us-east-1")
        service.invoke_response("What is my preference?", self.alice.bedrock_history)
        sent = client.converse_stream.call_args.kwargs["messages"]
        self.assertEqual(sent[0]["content"], [{"text": "remember my preference"}])
        self.assertEqual(len(self.alice.bedrock_history), 4)

    def test_busy_scope_does_not_follow_switch(self):
        scope = capture_scope(self.alice)
        scope.values["_turn_active"] = True
        _clear_conversation(self.alice)
        self.assertNotIn("_turn_active", capture_scope(self.alice).values)

    def test_reentrant_submission_is_ignored_and_lock_released(self):
        import streamlit as st
        from unittest.mock import patch
        calls = []
        @single_turn
        def submit():
            calls.append("once")
            self.assertFalse(submit())
            return True
        with patch.object(st, "session_state", self.alice):
            self.assertTrue(submit())
            self.assertTrue(submit())
        self.assertEqual(calls, ["once", "once"])
        self.assertNotIn("_turn_active", capture_scope(self.alice).values)
