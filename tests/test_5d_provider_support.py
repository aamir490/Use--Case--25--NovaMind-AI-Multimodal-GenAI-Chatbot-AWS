"""Task 5D offline checks for optional provider routing and text streaming."""
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from services.ai_provider import get_ai_service
from services.bedrock_service import GenerationError
from services.groq_service import GroqService
from services.provider_config import groq_model, groq_model_label, provider_for_model, selected_provider
from services.request_limits import RequestLimitError, validate_request
from tests.offline_support import demo_state, offline_guard


class TestProviderSelection(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_guard())
        self.identity = demo_state()["auth_session"]

    def test_model_routes_select_groq_and_bedrock(self):
        self.assertEqual(provider_for_model(groq_model()), "groq")
        self.assertEqual(provider_for_model("amazon.nova-micro-v1:0"), "bedrock")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}):
            self.assertIsInstance(get_ai_service(model_id=groq_model(), auth_session=self.identity), GroqService)
        expected = object()
        with patch("services.ai_provider.get_bedrock_service", return_value=expected):
            self.assertIs(get_ai_service(model_id="amazon.nova-micro-v1:0", auth_session=self.identity), expected)

    def test_environment_provider_is_validated(self):
        with patch.dict(os.environ, {"NOVAMIND_AI_PROVIDER": "groq"}):
            self.assertEqual(selected_provider(), "groq")
        with patch.dict(os.environ, {"NOVAMIND_AI_PROVIDER": "unknown"}):
            with self.assertRaisesRegex(ValueError, "NOVAMIND_AI_PROVIDER"):
                selected_provider()

    def test_gpt_oss_model_configuration_routes_and_stays_text_only(self):
        model = "openai/gpt-oss-120b"
        with patch.dict(os.environ, {"GROQ_MODEL": model, "GROQ_API_KEY": "test-only-key"}):
            self.assertEqual(groq_model(), model)
            self.assertEqual(groq_model_label(), "Groq Cloud (GPT-OSS 120B)")
            self.assertEqual(provider_for_model(model), "groq")
            service = get_ai_service(model_id=model, auth_session=self.identity)
            self.assertIsInstance(service, GroqService)
            self.assertEqual(service.model_id, model)
            with patch("services.groq_service.urlopen") as call:
                with self.assertRaises(GenerationError) as caught:
                    list(service.stream_response("question", [], image_bytes=b"x", image_format="png"))
            self.assertEqual(caught.exception.result.error_code, "RequestCapability")
            call.assert_not_called()
        with patch.dict(os.environ, {"GROQ_MODEL": "openai/gpt-oss-120b?secret=1"}):
            with self.assertRaisesRegex(ValueError, "supported model identifier"):
                groq_model()

    def test_nova_micro_rejects_multimodal_input(self):
        with self.assertRaises(RequestLimitError) as caught:
            validate_request("amazon.nova-micro-v1:0", "system", 128, 0.0,
                             [{"role": "user", "content": [
                                 {"image": {"format": "png", "source": {"bytes": b"x"}}},
                                 {"text": "describe"}]}])
        self.assertEqual(caught.exception.code, "RequestCapability")


class TestGroqStreaming(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_guard())
        self.identity = demo_state()["auth_session"]
        self.env = self.enterContext(patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}))
        self.service = GroqService(auth_session=self.identity)

    def test_missing_key_fails_without_network(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaisesRegex(GenerationError, "Set GROQ_API_KEY"):
                GroqService(auth_session=self.identity)

    def test_streaming_commits_history_and_usage(self):
        frames = [
            {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": " there"}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}},
        ]
        body = b"".join((b"data: " + json.dumps(frame).encode() + b"\n\n") for frame in frames) + b"data: [DONE]\n\n"
        history, usage = [], []
        with patch("services.groq_service.urlopen", return_value=io.BytesIO(body)) as call:
            self.assertEqual(list(self.service.stream_response("question", history, usage_records=usage)),
                             ["Hello", " there"])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["content"], [{"text": "Hello there"}])
        self.assertEqual((usage[0].input_tokens, usage[0].output_tokens), (4, 2))
        self.assertEqual(call.call_args.kwargs["timeout"], 60)
        request = call.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["max_completion_tokens"], self.service.max_tokens)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["model"], self.service.model_id)
        self.assertEqual(request.get_header("User-agent"), "NovaMindAI/1.0")
        self.assertEqual(request.get_header("Accept"), "text/event-stream")
        self.assertNotIn("test-only-key", request.data.decode())

    def test_http_api_error_is_classified_without_logging_provider_message(self):
        private_error = b'{"error":{"message":"PRIVATE_PROVIDER_DETAIL","type":"invalid_request_error"}}'
        error = HTTPError("https://api.groq.com/openai/v1/chat/completions", 400,
                          "Bad Request", {}, io.BytesIO(private_error))
        with patch("services.groq_service.urlopen", side_effect=error):
            with self.assertLogs("novamind.events", level="INFO") as captured:
                with self.assertRaises(GenerationError) as caught:
                    list(self.service.stream_response("question", []))
        event = json.loads(captured.records[-1].getMessage())
        self.assertEqual(caught.exception.result.error_code, "GroqHTTP400")
        self.assertEqual(event["error_category"], "validation")
        self.assertNotIn("PRIVATE_PROVIDER_DETAIL", captured.records[-1].getMessage())

    def test_attachments_are_rejected_before_network(self):
        with patch("services.groq_service.urlopen") as call:
            with self.assertRaises(GenerationError) as caught:
                list(self.service.stream_response("question", [], image_bytes=b"image", image_format="png"))
        self.assertEqual(caught.exception.result.error_code, "RequestCapability")
        call.assert_not_called()

