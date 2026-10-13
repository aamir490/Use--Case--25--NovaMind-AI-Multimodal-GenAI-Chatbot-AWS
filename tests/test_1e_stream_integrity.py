"""Task 1E offline service and frontend behavior tests; no live Streamlit/AWS."""

from tests.offline_support import demo_state
from tests.frontend_support import load_frontend

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError, EventStreamError
from services.bedrock_service import BedrockService, GenerationError
from utils.validators import export_conversation_as_text


def delta(text):
    return {"contentBlockDelta": {"delta": {"text": text}}}


def stop(reason="end_turn"):
    return {"messageStop": {"stopReason": reason}}


def denied():
    return ClientError({"Error": {"Code": "AccessDeniedException", "Message": "private detail"}}, "ConverseStream")


class FakeStream:
    def __init__(self, events, close_error=False):
        self.events = iter(events)
        self.closed = 0
        self.read = 0
        self.close_error = close_error

    def __iter__(self):
        return self

    def __next__(self):
        event = next(self.events)
        self.read += 1
        if isinstance(event, BaseException):
            raise event
        return event

    def close(self):
        self.closed += 1
        if self.close_error:
            raise RuntimeError("private cleanup detail")


class OfflineCase(unittest.TestCase):
    def setUp(self):
        from tests.offline_support import offline_guard
        self.enterContext(offline_guard())
        self.client = Mock(spec=["converse_stream"])
        with patch("services.bedrock_service.create_aws_client", return_value=self.client):
            self.service = BedrockService(auth_session=demo_state()["auth_session"], model_id="amazon.nova-pro-v1:0", region="us-east-1")

    def respond(self, events, **kwargs):
        stream = FakeStream(events, **kwargs)
        self.client.converse_stream.side_effect = None
        self.client.converse_stream.return_value = {"stream": stream}
        return stream

    def fail(self, history=None, **kwargs):
        history = [] if history is None else history
        previous = list(history)
        with self.assertRaises(GenerationError) as error:
            list(self.service.stream_response("question", history, **kwargs))
        self.assertEqual(history, previous)
        return error.exception.result


class TestStreamIntegrity(OfflineCase):
    def test_complete_response_commits_once_and_closes(self):
        stream = self.respond([delta("Hello "), delta("world"), stop(), {"metadata": {}}])
        history = []
        self.assertEqual(list(self.service.stream_response("hi", history)), ["Hello ", "world"])
        self.assertEqual(history, [
            {"role": "user", "content": [{"text": "hi"}]},
            {"role": "assistant", "content": [{"text": "Hello world"}]},
        ])
        self.assertEqual(stream.closed, 1)
        self.assertEqual(stream.read, 4)

    def test_stop_sequence_completes(self):
        self.respond([delta("done"), stop("stop_sequence")])
        history = []
        self.assertEqual(self.service.invoke_response("q", history), "done")
        self.assertEqual(len(history), 2)

    def test_empty_stream_fails(self):
        stream = self.respond([])
        result = self.fail()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "UnexpectedStreamEnd")
        self.assertEqual(stream.closed, 1)

    def test_missing_stop_preserves_partial_only(self):
        self.respond([delta("partial")])
        result = self.fail()
        self.assertEqual((result.status, result.text), ("incomplete", "partial"))
        self.assertEqual(result.error_code, "UnexpectedStreamEnd")

    def test_missing_stop_reason_fails(self):
        self.respond([delta("partial"), {"messageStop": {}}])
        self.assertEqual(self.fail().error_code, "UnsuccessfulStop")

    def test_non_success_stop_reasons_excluded(self):
        for reason in ("max_tokens", "guardrail_intervened", "content_filtered", "tool_use", "unknown"):
            with self.subTest(reason=reason):
                self.respond([delta("partial"), stop(reason)])
                result = self.fail()
                self.assertEqual(result.status, "incomplete")
                self.assertEqual(result.stop_reason, reason)

    def test_no_text_despite_success_stop_fails(self):
        self.respond([stop()])
        self.assertEqual(self.fail().error_code, "EmptyResponse")

    def test_whitespace_only_response_excluded(self):
        self.respond([delta("  "), stop()])
        self.assertEqual(self.fail().error_code, "EmptyResponse")

    def test_midstream_exception_is_not_model_text(self):
        stream = self.respond([delta("partial"), RuntimeError("private detail")])
        history = []
        generator = self.service.stream_response("q", history)
        self.assertEqual(next(generator), "partial")
        with self.assertRaises(GenerationError) as caught:
            next(generator)
        self.assertEqual(caught.exception.result.text, "partial")
        self.assertNotIn("private detail", str(caught.exception))
        self.assertEqual(history, [])
        self.assertEqual(stream.closed, 1)

    def test_call_failure_is_failed_and_safe(self):
        self.client.converse_stream.side_effect = RuntimeError("private detail")
        result = self.fail()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.text, "")
        self.assertNotIn("private detail", result.error_message)

    def test_raw_stream_error_events_fail(self):
        for key in ("internalServerException", "modelStreamErrorException", "validationException",
                    "throttlingException", "serviceUnavailableException"):
            with self.subTest(key=key):
                self.respond([delta("partial"), {key: {"message": "private detail"}}])
                self.assertEqual(self.fail().error_code, key)

    def test_sdk_eventstream_error_fails(self):
        error = EventStreamError({"Error": {"Code": "ModelStreamErrorException", "Message": "private"}}, "ConverseStream")
        self.respond([delta("partial"), error])
        self.assertEqual(self.fail().error_code, "ModelStreamErrorException")

    def test_error_after_stop_does_not_commit(self):
        self.respond([delta("answer"), stop(), RuntimeError("trailer failed")])
        self.assertEqual(self.fail().status, "incomplete")

    def test_duplicate_stop_rejected(self):
        self.respond([delta("answer"), stop(), stop()])
        self.assertEqual(self.fail().error_code, "InvalidStreamSequence")

    def test_text_after_stop_rejected(self):
        self.respond([delta("answer"), stop(), delta("extra")])
        self.assertEqual(self.fail().text, "answer")

    def test_unsupported_delta_not_committed(self):
        self.respond([{"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}}, stop()])
        self.assertEqual(self.fail().error_code, "UnsupportedOutput")

    def test_malformed_delta_not_committed(self):
        self.respond([delta(12), stop()])
        self.assertEqual(self.fail().error_code, "InvalidTextDelta")

    def test_no_fallback_after_text(self):
        stream = self.respond([delta("partial"), denied()])
        result = self.fail()
        self.assertEqual(result.text, "partial")
        self.client.converse_stream.assert_called_once()
        self.assertEqual(stream.closed, 1)

    def test_no_fallback_after_output_start_without_text(self):
        self.respond([{"contentBlockStart": {"start": {}}}, denied()])
        self.fail()
        self.client.converse_stream.assert_called_once()

    def test_no_fallback_after_empty_delta(self):
        self.respond([delta(""), denied()])
        self.fail()
        self.client.converse_stream.assert_called_once()

    def test_fallback_before_output_closes_first_stream(self):
        first = FakeStream([denied()])
        second = FakeStream([delta("ok"), stop()])
        def invoke(**kwargs):
            if kwargs["modelId"] == "amazon.nova-pro-v1:0":
                return {"stream": first}
            self.assertEqual(first.closed, 1)
            return {"stream": second}
        self.client.converse_stream.side_effect = invoke
        history = []
        self.assertEqual(self.service.invoke_response("q", history), "ok")
        self.assertEqual(len(history), 2)
        self.assertEqual(second.closed, 1)
        self.assertEqual(self.service.get_model_info()["last_used_model"], "us.amazon.nova-pro-v1:0")

    def test_fallback_failure_excludes_both_attempts(self):
        second = FakeStream([delta("partial"), RuntimeError("failed")])
        self.client.converse_stream.side_effect = [denied(), {"stream": second}]
        self.assertEqual(self.fail().status, "incomplete")
        self.assertEqual(self.client.converse_stream.call_count, 2)
        self.assertEqual(second.closed, 1)

    def test_direct_profile_does_not_retry(self):
        self.service.model_id = "us.amazon.nova-pro-v1:0"
        self.client.converse_stream.side_effect = denied()
        self.fail()
        self.client.converse_stream.assert_called_once()

    def test_generator_close_cleans_up_without_history(self):
        stream = self.respond([delta("partial"), stop()])
        history = []
        generator = self.service.stream_response("q", history)
        next(generator)
        generator.close()
        self.assertEqual(stream.closed, 1)
        self.assertEqual(history, [])

    def test_interruption_propagates_and_closes(self):
        stream = self.respond([delta("partial"), KeyboardInterrupt()])
        history = []
        with self.assertRaises(KeyboardInterrupt):
            list(self.service.stream_response("q", history))
        self.assertEqual(history, [])
        self.assertEqual(stream.closed, 1)

    def test_cleanup_failure_does_not_mask_primary_failure(self):
        stream = self.respond([delta("partial")], close_error=True)
        self.assertEqual(self.fail().error_code, "UnexpectedStreamEnd")
        self.assertEqual(stream.closed, 1)

    def test_cleanup_failure_does_not_duplicate_success(self):
        self.respond([delta("ok"), stop()], close_error=True)
        history = []
        self.assertEqual(self.service.invoke_response("q", history), "ok")
        self.assertEqual(len(history), 2)

    def test_followup_excludes_failed_multimodal_turn(self):
        self.respond([delta("prior"), stop()])
        history = []
        self.service.invoke_response("first", history)
        previous = list(history)
        self.respond([delta("bad partial")])
        self.fail(history, image_bytes=b"image", image_format="png", doc_bytes=b"doc", doc_name="Document 1")
        self.respond([delta("next"), stop()])
        self.service.invoke_response("followup", history)
        self.assertEqual(self.client.converse_stream.call_args.kwargs["messages"],
                         previous + [{"role": "user", "content": [{"text": "followup"}]}])

    def test_invoke_response_raises_with_partial(self):
        self.respond([delta("partial")])
        history = []
        with self.assertRaises(GenerationError) as caught:
            self.service.invoke_response("q", history)
        self.assertEqual(caught.exception.result.text, "partial")
        self.assertEqual(history, [])

    def test_previous_success_model_survives_failed_request(self):
        self.respond([delta("ok"), stop()])
        self.service.invoke_response("q", [])
        self.respond([delta("partial")])
        self.fail()
        self.assertEqual(self.service.get_model_info()["last_used_model"], "amazon.nova-pro-v1:0")


class SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class TestFrontendIntegrity(OfflineCase):
    def setUp(self):
        super().setUp()
        self.st = MagicMock()
        self.st.session_state = SessionState()
        self.ui = load_frontend(self.st, self)
        self.ui._init_session_state()
        self.ui._get_or_create_service = Mock(return_value=self.service)

    def isolate_metrics_placeholder(self):
        self.st.empty.side_effect = [self.st.empty.return_value, MagicMock()]

    def test_chat_success_records_completed_pair(self):
        self.respond([delta("answer"), stop()])
        self.ui._handle_user_input("question")
        self.assertEqual(len(self.st.session_state.bedrock_history), 2)
        self.assertEqual(self.st.session_state.chat_history[-1]["status"], "completed")
        self.assertEqual(self.st.session_state.chat_history[-1]["text"], "answer")

    def test_failed_chat_is_status_not_assistant_content(self):
        self.client.converse_stream.side_effect = RuntimeError("private detail")
        self.ui._handle_user_input("question")
        record = self.st.session_state.chat_history[-1]
        self.assertEqual((record["status"], record["text"]), ("failed", ""))
        self.assertTrue(record["error_message"])
        self.assertNotIn("private detail", str(record))
        self.assertEqual(self.st.session_state.bedrock_history, [])
        self.assertEqual(self.st.session_state.total_output_tokens, 0)

    def test_partial_chat_survives_rerender_as_incomplete(self):
        self.respond([delta("partial"), RuntimeError("failed")])
        self.ui._handle_user_input("question")
        record = self.st.session_state.chat_history[-1]
        self.assertEqual((record["status"], record["text"]), ("incomplete", "partial"))
        self.st.warning.reset_mock()
        self.st.markdown.reset_mock()
        self.ui._render_chat_history()
        self.st.warning.assert_called_once_with(record["error_message"])
        self.st.markdown.assert_any_call("partial")
        self.assertEqual(self.st.session_state.bedrock_history, [])

    def test_service_initialization_failure_is_safe(self):
        self.ui._get_or_create_service.side_effect = RuntimeError("private config")
        self.ui._handle_user_input("question")
        self.assertEqual(self.st.session_state.chat_history[-1]["status"], "failed")
        self.client.converse_stream.assert_not_called()

    def seed_history(self):
        self.st.session_state.bedrock_history[:] = [
            {"role": "user", "content": [{"text": "earlier"}]},
            {"role": "assistant", "content": [{"text": "answer"}]},
        ]
        self.st.session_state.chat_history[:] = [{"role": "user", "text": "earlier"},
                                               {"role": "assistant", "text": "answer"}]

    def test_summary_success_uses_same_commit_contract(self):
        self.seed_history()
        self.respond([delta("summary"), stop()])
        self.ui._handle_summary()
        self.assertEqual(len(self.st.session_state.bedrock_history), 4)
        self.assertEqual(self.st.session_state.chat_history[-1]["status"], "completed")
        self.assertEqual(self.st.session_state.total_output_tokens, 0)  # No metadata, not an estimate.
        self.assertIsNone(self.ui._session_cost())

    def test_failed_summary_preserves_original_context(self):
        self.seed_history()
        previous = list(self.st.session_state.bedrock_history)
        self.client.converse_stream.side_effect = denied()
        self.ui._handle_summary()
        self.assertEqual(self.st.session_state.bedrock_history, previous)
        self.assertEqual(self.st.session_state.chat_history[-1]["status"], "failed")

    def test_partial_summary_is_display_only(self):
        self.seed_history()
        previous = list(self.st.session_state.bedrock_history)
        self.respond([delta("partial summary")])
        self.ui._handle_summary()
        self.assertEqual(self.st.session_state.bedrock_history, previous)
        self.assertEqual(self.st.session_state.chat_history[-1]["text"], "partial summary")
        self.assertEqual(self.st.session_state.chat_history[-1]["status"], "incomplete")

    def test_summary_ignores_failed_only_display_history(self):
        self.st.session_state.chat_history[:] = [{"role": "assistant", "text": "partial", "status": "incomplete"}]
        self.ui._handle_summary()
        self.client.converse_stream.assert_not_called()
        self.st.info.assert_called_once()

    def test_renderer_failure_closes_generator_without_commit(self):
        stream = self.respond([delta("partial"), stop()])
        self.isolate_metrics_placeholder()
        self.st.empty.return_value.markdown.side_effect = [RuntimeError("render"), None]
        result = self.ui._stream_and_display_response("q", self.service, None, None)
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(self.st.session_state.bedrock_history, [])
        self.assertEqual(stream.closed, 1)

    def test_final_render_failure_does_not_publish_working_history(self):
        self.respond([delta("answer"), stop()])
        self.isolate_metrics_placeholder()
        self.st.empty.return_value.markdown.side_effect = [None, RuntimeError("render"), None]
        result = self.ui._stream_and_display_response("q", self.service, None, None)
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(self.st.session_state.bedrock_history, [])

    def test_ui_interruption_closes_stream(self):
        stream = self.respond([delta("partial"), stop()])
        self.isolate_metrics_placeholder()
        self.st.empty.return_value.markdown.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.ui._stream_and_display_response("q", self.service, None, None)
        self.assertEqual(stream.closed, 1)
        self.assertEqual(self.st.session_state.bedrock_history, [])

    def test_export_labels_unsuccessful_output(self):
        self.respond([delta("partial")])
        self.ui._handle_user_input("question")
        export = export_conversation_as_text(self.st.session_state.chat_history)
        self.assertIn("Response incomplete; excluded from AI context", export)
        self.assertIn("partial", export)

    def test_followup_and_summary_do_not_see_failed_turn(self):
        self.respond([delta("failed partial")])
        self.ui._handle_user_input("failed question")
        self.respond([delta("answer"), stop()])
        self.ui._handle_user_input("new question")
        self.assertEqual(self.client.converse_stream.call_args.kwargs["messages"],
                         [{"role": "user", "content": [{"text": "new question"}]}])
        self.respond([delta("summary"), stop()])
        self.ui._handle_summary()
        self.assertNotIn("failed question", str(self.client.converse_stream.call_args.kwargs["messages"]))
        self.assertNotIn("failed partial", str(self.client.converse_stream.call_args.kwargs["messages"]))


if __name__ == "__main__":
    unittest.main()
