"""
tests/test_1d_model_fallback.py
─────────────────────────────────
Task 1D regression tests — Bedrock model-routing and fallback policy.

Covers:
  A. _build_candidate_list — routing policy per model family
  B. Successful call — no fallback needed, last_used_model updated
  C. AccessDeniedException on Nova Pro — exactly one fallback attempted
  D. AccessDeniedException on Nova Pro — fallback succeeds
  E. AccessDeniedException on Nova Pro — double failure (both candidates denied)
  F. AccessDeniedException on Nova Lite — no fallback (single attempt only)
  G. AccessDeniedException on Claude — no fallback
  H. model_id never mutated across multiple calls
  I. Non-access error (ThrottlingException) — no retry, single failure
  J. History integrity — completed pairs appended once; failures excluded
  K. get_model_info — model_id stays user's choice; last_used reflects reality
  L. Partial stream + error — partial text is display-only (Task 1E)

All tests are fully offline (no network, no AWS, no Streamlit).
"""

from tests.offline_support import demo_state
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client_error(code: str, message: str = "test error") -> "botocore.exceptions.ClientError":
    import botocore.exceptions
    return botocore.exceptions.ClientError(
        {"Error": {"Code": code, "Message": message}}, "converse_stream"
    )


def _make_stream(*text_chunks: str) -> dict:
    """Return a fake converse_stream response dict with the given text chunks."""
    events = [
        {"contentBlockDelta": {"delta": {"text": chunk}}}
        for chunk in text_chunks
    ]
    events.append({"messageStop": {"stopReason": "end_turn"}})
    return {"stream": iter(events)}


def _make_service(model_id: str, client: Mock) -> "BedrockService":
    with patch("services.bedrock_service.create_aws_client", return_value=client):
        from services.bedrock_service import BedrockService
        return BedrockService(
            auth_session=demo_state()["auth_session"],
            region="us-east-1",
            model_id=model_id,
            max_tokens=128,
            temperature=0.0,
            system_prompt="Test assistant.",
        )


def _failed_call(service, text, history):
    """Task 1E: errors are raised, never yielded as assistant content."""
    from services.bedrock_service import GenerationError
    with unittest.TestCase().assertRaises(GenerationError) as caught:
        list(service.stream_response(text, history))
    return caught.exception


# ═════════════════════════════════════════════════════════════════════════════
# A. _build_candidate_list — routing policy
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildCandidateList(unittest.TestCase):

    def _svc(self, model_id: str):
        with patch("services.bedrock_service.create_aws_client"):
            from services.bedrock_service import BedrockService
            return BedrockService(auth_session=demo_state()["auth_session"], model_id=model_id)

    def test_nova_pro_base_gets_two_candidates(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID
        svc = self._svc(_NOVA_PRO_BASE_ID)
        candidates = svc._build_candidate_list()
        self.assertEqual(candidates, [_NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID])

    def test_nova_pro_first_candidate_is_base_id(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        svc = self._svc(_NOVA_PRO_BASE_ID)
        self.assertEqual(svc._build_candidate_list()[0], _NOVA_PRO_BASE_ID)

    def test_nova_lite_gets_one_candidate(self):
        svc = self._svc("amazon.nova-lite-v1:0")
        self.assertEqual(svc._build_candidate_list(), ["amazon.nova-lite-v1:0"])

    def test_claude_gets_one_candidate(self):
        svc = self._svc("anthropic.claude-3-5-sonnet-20241022-v2:0")
        self.assertEqual(
            svc._build_candidate_list(),
            ["anthropic.claude-3-5-sonnet-20241022-v2:0"],
        )

    def test_custom_model_gets_one_candidate(self):
        svc = self._svc("custom.my-model-v1:0")
        self.assertEqual(svc._build_candidate_list(), ["custom.my-model-v1:0"])

    def test_candidate_list_never_longer_than_two(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        for model in [_NOVA_PRO_BASE_ID, "amazon.nova-lite-v1:0",
                      "anthropic.claude-3-5-sonnet-20241022-v2:0"]:
            svc = self._svc(model)
            self.assertLessEqual(len(svc._build_candidate_list()), 2)


# ═════════════════════════════════════════════════════════════════════════════
# B. Successful call — no fallback needed
# ═════════════════════════════════════════════════════════════════════════════

class TestSuccessfulCall(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        self.client = Mock(spec=["converse_stream"])
        self.client.converse_stream.return_value = _make_stream("Hello ", "world!")
        self.service = _make_service(_NOVA_PRO_BASE_ID, self.client)
        self.model_id = _NOVA_PRO_BASE_ID

    def test_chunks_yielded(self):
        chunks = list(self.service.stream_response("hi", []))
        self.assertEqual("".join(chunks), "Hello world!")

    def test_only_one_api_call_made(self):
        list(self.service.stream_response("hi", []))
        self.assertEqual(self.client.converse_stream.call_count, 1)

    def test_first_call_uses_configured_model(self):
        list(self.service.stream_response("hi", []))
        call_kwargs = self.client.converse_stream.call_args[1]
        self.assertEqual(call_kwargs["modelId"], self.model_id)

    def test_last_used_model_updated_on_success(self):
        list(self.service.stream_response("hi", []))
        self.assertEqual(self.service._last_used_model_id, self.model_id)

    def test_model_id_unchanged_after_success(self):
        list(self.service.stream_response("hi", []))
        self.assertEqual(self.service.model_id, self.model_id)

    def test_history_has_two_entries(self):
        h = []
        list(self.service.stream_response("hi", h))
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]["role"], "user")
        self.assertEqual(h[1]["role"], "assistant")

    def test_history_assistant_content_matches_reply(self):
        h = []
        list(self.service.stream_response("hi", h))
        self.assertEqual(h[1]["content"][0]["text"], "Hello world!")


# ═════════════════════════════════════════════════════════════════════════════
# C. AccessDeniedException on Nova Pro — exactly one fallback attempted
# ═════════════════════════════════════════════════════════════════════════════

class TestNovaProFallbackAttempted(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID
        self.base_id    = _NOVA_PRO_BASE_ID
        self.profile_id = _NOVA_PRO_PROFILE_ID

        self.client = Mock(spec=["converse_stream"])
        # Both attempts denied
        self.client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
        self.service = _make_service(self.base_id, self.client)

    def test_exactly_two_api_calls(self):
        _failed_call(self.service, "hi", [])
        self.assertEqual(self.client.converse_stream.call_count, 2)

    def test_first_call_uses_base_model(self):
        _failed_call(self.service, "hi", [])
        first_call = self.client.converse_stream.call_args_list[0]
        self.assertEqual(first_call[1]["modelId"], self.base_id)

    def test_second_call_uses_inference_profile(self):
        _failed_call(self.service, "hi", [])
        second_call = self.client.converse_stream.call_args_list[1]
        self.assertEqual(second_call[1]["modelId"], self.profile_id)

    def test_no_third_call(self):
        """The fallback must be bounded at one retry."""
        _failed_call(self.service, "hi", [])
        self.assertLessEqual(self.client.converse_stream.call_count, 2)


# ═════════════════════════════════════════════════════════════════════════════
# D. AccessDeniedException on Nova Pro — fallback succeeds
# ═════════════════════════════════════════════════════════════════════════════

class TestNovaProFallbackSucceeds(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID
        self.base_id    = _NOVA_PRO_BASE_ID
        self.profile_id = _NOVA_PRO_PROFILE_ID

        self.client = Mock(spec=["converse_stream"])
        # First call: AccessDeniedException; second call: success
        self.client.converse_stream.side_effect = [
            _make_client_error("AccessDeniedException"),
            _make_stream("Fallback ", "response."),
        ]
        self.service = _make_service(self.base_id, self.client)

    def test_successful_reply_yielded(self):
        chunks = list(self.service.stream_response("hi", []))
        self.assertEqual("".join(chunks), "Fallback response.")

    def test_last_used_model_is_profile_after_fallback(self):
        list(self.service.stream_response("hi", []))
        self.assertEqual(self.service._last_used_model_id, self.profile_id)

    def test_model_id_still_base_id_after_fallback(self):
        """User's configured choice must never change."""
        list(self.service.stream_response("hi", []))
        self.assertEqual(self.service.model_id, self.base_id)

    def test_history_contains_successful_reply(self):
        h = []
        list(self.service.stream_response("hi", h))
        self.assertEqual(h[1]["content"][0]["text"], "Fallback response.")

    def test_next_call_retries_base_model_not_profile(self):
        """
        After a successful fallback, the NEXT call must start fresh with the
        base model ID, not permanently use the profile.
        """
        # First request: base denied → profile succeeds
        self.client.converse_stream.side_effect = [
            _make_client_error("AccessDeniedException"),
            _make_stream("first fallback"),
            # Second request: base succeeds
            _make_stream("second success"),
        ]
        list(self.service.stream_response("first", []))
        list(self.service.stream_response("second", []))

        third_call = self.client.converse_stream.call_args_list[2]
        self.assertEqual(third_call[1]["modelId"], self.base_id,
                         "Second request should start with base model, not profile")


# ═════════════════════════════════════════════════════════════════════════════
# E. Double failure — both candidates denied
# ═════════════════════════════════════════════════════════════════════════════

class TestNovaProDoubleFailed(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        self.client = Mock(spec=["converse_stream"])
        self.client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
        self.service = _make_service(_NOVA_PRO_BASE_ID, self.client)

    def test_error_message_raised(self):
        chunks = _failed_call(self.service, "hi", [])
        combined = chunks.result.error_code
        self.assertIn("AccessDeniedException", combined)

    def test_history_unchanged_on_error(self):
        h = []
        _failed_call(self.service, "hi", h)
        self.assertEqual(h, [])

    def test_model_id_not_mutated(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        _failed_call(self.service, "hi", [])
        self.assertEqual(self.service.model_id, _NOVA_PRO_BASE_ID)

    def test_last_used_model_is_none_after_double_failure(self):
        _failed_call(self.service, "hi", [])
        self.assertIsNone(self.service._last_used_model_id)


# ═════════════════════════════════════════════════════════════════════════════
# F. AccessDeniedException on Nova Lite — no fallback
# ═════════════════════════════════════════════════════════════════════════════

class TestNovaLiteNoFallback(unittest.TestCase):

    def setUp(self):
        self.client = Mock(spec=["converse_stream"])
        self.client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
        self.service = _make_service("amazon.nova-lite-v1:0", self.client)

    def test_single_api_call_only(self):
        _failed_call(self.service, "hi", [])
        self.assertEqual(self.client.converse_stream.call_count, 1)

    def test_model_id_unchanged(self):
        _failed_call(self.service, "hi", [])
        self.assertEqual(self.service.model_id, "amazon.nova-lite-v1:0")

    def test_no_nova_pro_substitution(self):
        """Nova Pro must NEVER be called when the user selected Nova Lite."""
        from services.bedrock_service import _NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID
        _failed_call(self.service, "hi", [])
        for c in self.client.converse_stream.call_args_list:
            self.assertNotIn(c[1]["modelId"], [_NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID])

    def test_error_raised(self):
        chunks = _failed_call(self.service, "hi", [])
        self.assertIn("AccessDeniedException", chunks.result.error_code)


# ═════════════════════════════════════════════════════════════════════════════
# G. AccessDeniedException on Claude — no fallback
# ═════════════════════════════════════════════════════════════════════════════

class TestClaudeNoFallback(unittest.TestCase):

    def setUp(self):
        self.model = "anthropic.claude-3-5-sonnet-20241022-v2:0"
        self.client = Mock(spec=["converse_stream"])
        self.client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
        self.service = _make_service(self.model, self.client)

    def test_single_call_only(self):
        _failed_call(self.service, "hi", [])
        self.assertEqual(self.client.converse_stream.call_count, 1)

    def test_model_id_unchanged(self):
        _failed_call(self.service, "hi", [])
        self.assertEqual(self.service.model_id, self.model)


# ═════════════════════════════════════════════════════════════════════════════
# H. model_id immutability across multiple calls
# ═════════════════════════════════════════════════════════════════════════════

class TestModelIdImmutability(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        self.base_id = _NOVA_PRO_BASE_ID
        self.client = Mock(spec=["converse_stream"])

    def test_model_id_unchanged_after_10_successful_calls(self):
        self.client.converse_stream.return_value = _make_stream("ok")
        svc = _make_service(self.base_id, self.client)
        for _ in range(10):
            self.client.converse_stream.return_value = _make_stream("ok")
            list(svc.stream_response("hi", []))
        self.assertEqual(svc.model_id, self.base_id)

    def test_model_id_unchanged_after_10_failed_calls(self):
        self.client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
        svc = _make_service(self.base_id, self.client)
        for _ in range(10):
            _failed_call(svc, "hi", [])
        self.assertEqual(svc.model_id, self.base_id)

    def test_model_id_unchanged_after_mixed_success_failure(self):
        svc = _make_service(self.base_id, self.client)
        for i in range(6):
            if i % 2 == 0:
                self.client.converse_stream.side_effect = None
                self.client.converse_stream.return_value = _make_stream("ok")
            else:
                self.client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
            if i % 2 == 0:
                list(svc.stream_response("hi", []))
            else:
                _failed_call(svc, "hi", [])
        self.assertEqual(svc.model_id, self.base_id)


# ═════════════════════════════════════════════════════════════════════════════
# I. Non-access error — no retry
# ═════════════════════════════════════════════════════════════════════════════

class TestNonAccessErrorNoRetry(unittest.TestCase):

    def test_throttling_exception_single_attempt(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = _make_client_error("ThrottlingException")
        svc = _make_service(_NOVA_PRO_BASE_ID, client)
        chunks = _failed_call(svc, "hi", [])
        self.assertEqual(client.converse_stream.call_count, 1)
        self.assertIn("ThrottlingException", chunks.result.error_code)

    def test_validation_exception_single_attempt(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = _make_client_error("ValidationException")
        svc = _make_service(_NOVA_PRO_BASE_ID, client)
        chunks = _failed_call(svc, "hi", [])
        self.assertEqual(client.converse_stream.call_count, 1)

    def test_unexpected_exception_single_attempt(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = RuntimeError("network timeout")
        svc = _make_service(_NOVA_PRO_BASE_ID, client)
        chunks = _failed_call(svc, "hi", [])
        self.assertEqual(client.converse_stream.call_count, 1)
        self.assertIn("UnexpectedError", chunks.result.error_code)


# ═════════════════════════════════════════════════════════════════════════════
# J. History integrity
# ═════════════════════════════════════════════════════════════════════════════

class TestHistoryIntegrity(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        self.base_id = _NOVA_PRO_BASE_ID

    def _svc_success(self, *chunks):
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = lambda **kwargs: _make_stream(*chunks)
        return _make_service(self.base_id, client), client

    def _svc_denied(self):
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = _make_client_error("AccessDeniedException")
        return _make_service(self.base_id, client), client

    def test_history_appended_exactly_once_per_call(self):
        svc, _ = self._svc_success("A")
        h = []
        list(svc.stream_response("turn1", h))
        list(svc.stream_response("turn2", h))
        self.assertEqual(len(h), 4)  # 2 user + 2 assistant

    def test_history_user_content_matches_input(self):
        svc, _ = self._svc_success("reply")
        h = []
        list(svc.stream_response("my question", h))
        user_content = h[0]["content"]
        text_blocks = [b["text"] for b in user_content if "text" in b]
        self.assertIn("my question", text_blocks)

    def test_history_correct_after_fallback_failure(self):
        svc, _ = self._svc_denied()
        h = []
        _failed_call(svc, "question", h)
        self.assertEqual(h, [])

    def test_history_not_duplicated_on_fallback_success(self):
        """Fallback success must add exactly 2 entries, not 4."""
        from services.bedrock_service import _NOVA_PRO_BASE_ID
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = [
            _make_client_error("AccessDeniedException"),
            _make_stream("success"),
        ]
        svc = _make_service(_NOVA_PRO_BASE_ID, client)
        h = []
        list(svc.stream_response("question", h))
        self.assertEqual(len(h), 2, f"Expected 2 history entries, got {len(h)}")

    def test_pre_existing_history_preserved(self):
        svc, _ = self._svc_success("new reply")
        existing = [
            {"role": "user",      "content": [{"text": "old question"}]},
            {"role": "assistant", "content": [{"text": "old answer"}]},
        ]
        h = list(existing)
        list(svc.stream_response("new question", h))
        # First 2 entries must be the original history
        self.assertEqual(h[0]["content"][0]["text"], "old question")
        self.assertEqual(h[1]["content"][0]["text"], "old answer")

    def test_history_sent_to_api_includes_pre_existing(self):
        """The API payload must include prior history turns."""
        client = Mock(spec=["converse_stream"])
        client.converse_stream.return_value = _make_stream("response")
        svc = _make_service(self.base_id, client)

        prior = [
            {"role": "user",      "content": [{"text": "prior question"}]},
            {"role": "assistant", "content": [{"text": "prior answer"}]},
        ]
        h = list(prior)
        list(svc.stream_response("new", h))
        call_messages = client.converse_stream.call_args[1]["messages"]
        # First two messages must be the prior history
        self.assertEqual(call_messages[0]["content"][0]["text"], "prior question")
        self.assertEqual(call_messages[1]["content"][0]["text"], "prior answer")


# ═════════════════════════════════════════════════════════════════════════════
# K. get_model_info
# ═════════════════════════════════════════════════════════════════════════════

class TestGetModelInfo(unittest.TestCase):

    def setUp(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID
        self.base_id    = _NOVA_PRO_BASE_ID
        self.profile_id = _NOVA_PRO_PROFILE_ID

    def test_model_id_is_configured_choice_before_any_call(self):
        with patch("services.bedrock_service.create_aws_client"):
            from services.bedrock_service import BedrockService
            svc = BedrockService(auth_session=demo_state()["auth_session"], model_id=self.base_id)
        info = svc.get_model_info()
        self.assertEqual(info["model_id"], self.base_id)

    def test_last_used_model_none_before_any_call(self):
        with patch("services.bedrock_service.create_aws_client"):
            from services.bedrock_service import BedrockService
            svc = BedrockService(auth_session=demo_state()["auth_session"], model_id=self.base_id)
        self.assertIsNone(svc.get_model_info()["last_used_model"])

    def test_model_id_unchanged_after_fallback_success(self):
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = [
            _make_client_error("AccessDeniedException"),
            _make_stream("ok"),
        ]
        svc = _make_service(self.base_id, client)
        list(svc.stream_response("hi", []))
        self.assertEqual(svc.get_model_info()["model_id"], self.base_id)

    def test_last_used_reflects_actual_model_after_fallback(self):
        client = Mock(spec=["converse_stream"])
        client.converse_stream.side_effect = [
            _make_client_error("AccessDeniedException"),
            _make_stream("ok"),
        ]
        svc = _make_service(self.base_id, client)
        list(svc.stream_response("hi", []))
        self.assertEqual(svc.get_model_info()["last_used_model"], self.profile_id)

    def test_last_used_reflects_base_after_direct_success(self):
        client = Mock(spec=["converse_stream"])
        client.converse_stream.return_value = _make_stream("ok")
        svc = _make_service(self.base_id, client)
        list(svc.stream_response("hi", []))
        self.assertEqual(svc.get_model_info()["last_used_model"], self.base_id)


# ═════════════════════════════════════════════════════════════════════════════
# L. Partial stream then unexpected error
# ═════════════════════════════════════════════════════════════════════════════

class TestPartialStream(unittest.TestCase):

    def test_unexpected_mid_stream_exception_excluded_from_history(self):
        from services.bedrock_service import _NOVA_PRO_BASE_ID

        def _bad_stream():
            yield {"contentBlockDelta": {"delta": {"text": "partial "}}}
            raise RuntimeError("mid-stream failure")

        client = Mock(spec=["converse_stream"])
        client.converse_stream.return_value = {"stream": _bad_stream()}
        svc = _make_service(_NOVA_PRO_BASE_ID, client)
        h = []
        error = _failed_call(svc, "hi", h)
        self.assertEqual(h, [])
        self.assertEqual(error.result.text, "partial ")
        self.assertEqual(error.result.status, "incomplete")


# ═════════════════════════════════════════════════════════════════════════════
# M. Regression
# ═════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    unittest.main(verbosity=2)
