"""Offline request admission and model-switch regressions."""

from tests.frontend_support import load_frontend
import copy
import importlib.util
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import test_1e_stream_integrity as fixtures
from services.bedrock_service import GenerationError
from services import request_limits as limits


def message(text="question"):
    return {"role": "user", "content": [{"text": text}]}


def image(size=1):
    return {"image": {"format": "png", "source": {"bytes": b"x" * size}}}


def document(size=1):
    return {"document": {"format": "pdf", "name": "Document 1", "source": {"bytes": b"x" * size}}}


class TestRequestLimits(fixtures.OfflineCase):
    def reject(self, code, history=None, **kwargs):
        history = [] if history is None else history
        before = copy.deepcopy(history)
        records = []
        with self.assertRaises(GenerationError) as caught:
            self.service.invoke_response("question", history, usage_records=records, **kwargs)
        self.assertEqual(caught.exception.result.error_code, code)
        self.assertIn("history was not changed", caught.exception.result.error_message)
        self.assertEqual(history, before)
        self.assertEqual(records, [])
        self.client.converse_stream.assert_not_called()

    def test_unknown_model_rejected_without_fallback(self):
        self.service.model_id = "unregistered-model"
        self.reject("RequestUnknownModel")

    def test_invalid_output_settings(self):
        for value in (0, -1, 8193, True, 1.5, "2048"):
            with self.subTest(value=value):
                self.service.max_tokens = value
                self.reject("RequestOutputBudget")

    def test_maximum_output_accepted(self):
        self.service.max_tokens = 8192
        self.respond([fixtures.delta("ok"), fixtures.stop()])
        self.assertEqual(self.service.invoke_response("q", []), "ok")
        self.assertEqual(self.client.converse_stream.call_args.kwargs["inferenceConfig"]["maxTokens"], 8192)

    def test_temperature_validation(self):
        for value in (float("nan"), float("inf"), -1, 1.1, True):
            self.service.temperature = value
            self.reject("RequestSettings")

    def test_context_includes_system_history_and_reserved_output(self):
        self.service.system_prompt = "s" * 70000
        self.reject("RequestContextBudget", [message("x" * 60000)])

    def test_context_exact_boundary_and_one_over(self):
        model = self.service.model_id
        policy = limits.MODEL_POLICIES[model]
        length = policy.context_budget - 256 - 128 - 8192
        limits.validate_request(model, "", 8192, 0.7, [message("x" * length)])
        with self.assertRaises(limits.RequestLimitError) as caught:
            limits.validate_request(model, "", 8192, 0.7, [message("x" * (length + 1))])
        self.assertEqual(caught.exception.code, "RequestContextBudget")

    def test_utf8_bytes_not_character_count(self):
        with self.assertRaises(limits.RequestLimitError):
            limits.validate_request(self.service.model_id, "", 2048, 0.7, [message("😀" * 40000)])

    def test_retained_history_rechecked_after_switch(self):
        history = [message("x" * 70000), {"role": "assistant", "content": [{"text": "ok"}]}]
        limits.validate_request(self.service.model_id, "", 2048, 0.7, history + [message()])
        self.service.model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
        self.reject("RequestContextBudget", history)

    def test_retained_attachment_capability_rechecked(self):
        policy = replace(limits.MODEL_POLICIES[self.service.model_id], images=frozenset())
        with patch.dict(limits.MODEL_POLICIES, {self.service.model_id: policy}):
            history = [message()]
            history[0]["content"].insert(0, image())
            self.reject("RequestCapability", history)

    def test_document_format_not_in_policy(self):
        self.reject("RequestCapability", doc_bytes=b"data", doc_format="unsupported")

    def test_aggregate_image_count_includes_retained_history(self):
        history = [message()]
        history[0]["content"] = [image() for _ in range(20)] + [{"text": "old"}]
        self.reject("RequestAttachmentCount", history, image_bytes=b"new", image_format="png")

    def test_aggregate_document_count(self):
        history = [message()]
        history[0]["content"] = [document() for _ in range(5)] + [{"text": "old"}]
        self.reject("RequestAttachmentCount", history, doc_bytes=b"new")

    def test_retained_oversized_attachment(self):
        history = [message()]
        history[0]["content"].insert(0, image(limits.IMAGE_BYTES + 1))
        self.reject("RequestAttachmentSize", history)

    def test_serialized_payload_boundary_includes_base64_and_escaping(self):
        messages = [message('"\\' * 100)]
        messages[0]["content"].insert(0, image(301))
        args = (self.service.model_id, "", 2048, 0.7, messages)
        size = limits.validate_request(*args)["payload_bytes"]
        self.assertGreater(size, 600)
        with patch.object(limits, "MAX_PAYLOAD_BYTES", size):
            limits.validate_request(*args)
        with patch.object(limits, "MAX_PAYLOAD_BYTES", size - 1), self.assertRaises(limits.RequestLimitError) as caught:
            limits.validate_request(*args)
        self.assertEqual(caught.exception.code, "RequestPayloadBudget")

    def test_payload_failure_before_client_call(self):
        with patch.object(limits, "MAX_PAYLOAD_BYTES", 10):
            self.reject("RequestPayloadBudget")

    def test_message_count_budget(self):
        self.reject("RequestMessageBudget", [message() for _ in range(limits.MAX_MESSAGES)])

    def test_unsupported_retained_tool_content_rejected(self):
        self.reject("RequestCapability", [{"role": "assistant", "content": [{"toolUse": {}}]}])

    def test_missing_attachment_fields_rejected(self):
        for kwargs in ({"image_bytes": b"x"}, {"image_format": "png"}, {"image_bytes": b"", "image_format": "png"}, {"doc_bytes": b""}):
            self.reject("RequestStructure", **kwargs)

    def test_malformed_history_rejected(self):
        for history in ([{"role": "system", "content": [{"text": "x"}]}],
                        [{"role": "user", "content": []}],
                        [{"role": "user", "content": [{"image": {"format": "png", "source": {"s3Location": "x"}}}]}]):
            self.reject("RequestStructure", history)

    def test_summary_validates_same_history(self):
        self.reject("RequestContextBudget", [message("x" * 128000)], operation="summary")

    def test_new_attachments_remain_valid(self):
        self.respond([fixtures.delta("ok"), fixtures.stop()])
        self.service.invoke_response("describe", [], image_bytes=b"image", image_format="png", doc_bytes=b"document")
        content = self.client.converse_stream.call_args.kwargs["messages"][-1]["content"]
        self.assertEqual([next(iter(b)) for b in content], ["image", "document", "text"])


class TestFrontendRequestLimits(fixtures.OfflineCase):
    def setUp(self):
        super().setUp()
        self.st = MagicMock()
        self.st.session_state = fixtures.SessionState()
        self.ui = load_frontend(self.st, self)
        self.ui._init_session_state()
        self.ui._get_or_create_service = Mock(return_value=self.service)

    def test_rejection_shows_reason_preserves_context_and_no_usage(self):
        history = [message("x" * 128000)]
        self.st.session_state.bedrock_history[:] = copy.deepcopy(history)
        self.ui._handle_user_input("q")
        result = self.st.session_state.chat_history[-1]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "RequestContextBudget")
        self.assertIn("Estimated context", result["error_message"])
        self.assertEqual(self.st.session_state.bedrock_history, history)
        self.assertEqual(self.st.session_state.usage_ledger, [])
        self.client.converse_stream.assert_not_called()

    def test_model_switch_warning_does_not_trim_history(self):
        history = [message("x" * 70000)]
        self.st.session_state.bedrock_history[:] = copy.deepcopy(history)
        self.assertIsNone(self.ui._model_context_warning("amazon.nova-pro-v1:0"))
        self.assertIn("Estimated context", self.ui._model_context_warning("anthropic.claude-3-5-sonnet-20241022-v2:0"))
        self.assertEqual(self.st.session_state.bedrock_history, history)
        self.client.converse_stream.assert_not_called()
