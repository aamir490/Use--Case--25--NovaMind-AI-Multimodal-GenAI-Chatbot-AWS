"""Offline Task 1F regressions. Uses existing fake streams and AWS/network guards."""

from tests.frontend_support import load_frontend
import unittest
import importlib.util
from pathlib import Path
from dataclasses import FrozenInstanceError
from decimal import Decimal
from unittest.mock import patch, MagicMock, Mock

import test_1e_stream_integrity as fixtures
from services.bedrock_service import GenerationError
from services.usage_accounting import MODEL_PRICING


def metadata(inp=1000, out=100, **extra):
    return {"metadata": {"usage": {"inputTokens": inp, "outputTokens": out,
                                  "totalTokens": inp + out}, **extra}}


class TestUsageService(fixtures.OfflineCase):
    def generate(self, events, **kwargs):
        self.respond(events)
        records = []
        self.service.invoke_response("short", [], usage_records=records, **kwargs)
        return records[0]

    def test_actual_counts_include_full_request_not_text_length(self):
        record = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata()])
        self.assertEqual((record.input_tokens, record.output_tokens, record.total_tokens), (1000, 100, 1100))
        self.assertEqual(record.cost_usd, Decimal("0.00112"))
        self.assertEqual(record.operation, "chat")
        self.assertEqual(record.stop_reason, "end_turn")
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.model_id, self.service.model_id)
        self.assertEqual(record.cost_status, "configured_rate_estimate")

    def test_summary_and_invoke_sink(self):
        record = self.generate([fixtures.delta("summary"), fixtures.stop(), metadata()], operation="summary")
        self.assertEqual(record.operation, "summary")
        self.assertEqual(record.input_tokens, 1000)

    def test_generator_return_carries_metadata(self):
        self.respond([fixtures.delta("ok"), fixtures.stop("stop_sequence"), metadata()])
        generator = self.service.stream_response("q", [])
        self.assertEqual(next(generator), "ok")
        with self.assertRaises(StopIteration) as caught:
            next(generator)
        result = caught.exception.value
        self.assertEqual(result.stop_reason, "stop_sequence")
        self.assertEqual(result.usage_records[0].output_tokens, 100)

    def test_missing_usage_is_unknown_not_zero(self):
        r = self.generate([fixtures.delta("ok"), fixtures.stop()])
        self.assertIsNone(r.input_tokens)
        self.assertIsNone(r.output_tokens)
        self.assertIsNone(r.cost_usd)
        self.assertEqual(r.cost_status, "unknown")

    def test_zero_usage_is_valid(self):
        r = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata(0, 0)])
        self.assertEqual(r.cost_usd, Decimal(0))
        self.assertEqual(r.input_tokens, 0)

    def test_malformed_metadata_does_not_break_success(self):
        for payload in (None, [], {}, {"usage": None}, {"usage": []},
                        {"usage": {"inputTokens": True, "outputTokens": 2}},
                        {"usage": {"inputTokens": -1, "outputTokens": 2}},
                        {"usage": {"inputTokens": "3", "outputTokens": 2}},
                        {"usage": {"inputTokens": 3.0, "outputTokens": 2}},
                        {"usage": {"inputTokens": 3}},
                        {"usage": {"inputTokens": 3, "outputTokens": 2, "totalTokens": 6}},
                        {"usage": {"inputTokens": 3, "outputTokens": 2, "totalTokens": False}},
                        {**metadata()["metadata"], "performanceConfig": None},
                        {**metadata()["metadata"], "serviceTier": "bad"}):
            with self.subTest(payload=payload):
                r = self.generate([fixtures.delta("ok"), fixtures.stop(), {"metadata": payload}])
                self.assertEqual(r.status, "completed")
                self.assertIsNone(r.cost_usd)

    def test_total_optional_input_output_sufficient(self):
        r = self.generate([fixtures.delta("ok"), fixtures.stop(),
                           {"metadata": {"usage": {"inputTokens": 1000, "outputTokens": 100}}}])
        self.assertEqual(r.cost_usd, Decimal("0.00112"))
        self.assertIsNone(r.total_tokens)

    def test_duplicate_metadata_not_double_counted(self):
        r = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata(), metadata(), metadata()])
        self.assertIsNone(r.input_tokens)
        self.assertIsNone(r.cost_usd)

    def test_unknown_model_and_region_have_no_default_price(self):
        # Explicit test capability registration does not invent a pricing entry.
        from services.request_limits import MODEL_POLICIES, ModelPolicy
        registration = patch.dict(MODEL_POLICIES, {"custom-model": ModelPolicy(128000)})
        registration.start()
        self.addCleanup(registration.stop)
        for model, region in (("custom-model", "us-east-1"), ("amazon.nova-pro-v1:0", "eu-west-1")):
            self.service.model_id, self.service.region = model, region
            r = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata()])
            self.assertEqual(r.input_tokens, 1000)
            self.assertIsNone(r.cost_usd)
            self.assertIsNone(r.input_rate)

    def test_cache_or_nonstandard_pricing_is_unknown(self):
        for extra in ({"cacheReadInputTokens": 10}, {"cacheWriteInputTokens": 4},
                      {"cacheDetails": [{"inputTokens": 5}]}):
            event = metadata()
            event["metadata"]["usage"].update(extra)
            r = self.generate([fixtures.delta("ok"), fixtures.stop(), event])
            self.assertIsNone(r.cost_usd)
            self.assertEqual(r.input_tokens, 1000)
        for extra in ({"performanceConfig": {"latency": "optimized"}},
                      {"serviceTier": {"type": "priority"}}):
            r = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata(**extra)])
            self.assertIsNone(r.cost_usd)

    def test_standard_metadata_price(self):
        r = self.generate([fixtures.delta("ok"), fixtures.stop(),
                           metadata(performanceConfig={"latency": "standard"}, serviceTier={"type": "default"})])
        self.assertEqual(r.cost_usd, Decimal("0.00112"))

    def test_failure_after_metadata_preserves_usage_and_history_integrity(self):
        for ending in (fixtures.stop("max_tokens"), RuntimeError("private")):
            self.respond([fixtures.delta("partial"), metadata(), ending])
            records, history = [], []
            with self.assertRaises(GenerationError) as caught:
                self.service.invoke_response("q", history, usage_records=records)
            self.assertEqual(history, [])
            self.assertEqual(records[0].cost_usd, Decimal("0.00112"))
            self.assertEqual(caught.exception.result.usage_records, tuple(records))
            self.assertEqual(records[0].status, "incomplete")

    def test_failed_empty_output_can_still_have_usage(self):
        self.respond([fixtures.stop(), metadata(20, 0)])
        with self.assertRaises(GenerationError) as caught:
            self.service.invoke_response("q", [])
        self.assertEqual(caught.exception.result.status, "failed")
        self.assertEqual(caught.exception.result.usage_records[0].input_tokens, 20)

    def test_fallback_preserves_both_attempts_actual_models(self):
        self.client.converse_stream.side_effect = [
            fixtures.denied(),
            {"stream": fixtures.FakeStream([fixtures.delta("ok"), fixtures.stop(), metadata()])},
        ]
        records = []
        self.service.invoke_response("q", [], usage_records=records)
        self.assertEqual(len(records), 2)
        self.assertEqual([r.attempt for r in records], [1, 2])
        self.assertEqual(records[0].request_id, records[1].request_id)
        self.assertEqual(records[1].model_id, "us.amazon.nova-pro-v1:0")
        self.assertEqual(records[1].cost_usd, Decimal("0.00112"))
        self.assertIsNone(records[0].cost_usd)
        self.assertEqual(records[0].status, "failed")

    def test_failed_fallback_carries_all_attempts(self):
        self.client.converse_stream.side_effect = [fixtures.denied(), fixtures.denied()]
        with self.assertRaises(GenerationError) as caught:
            self.service.invoke_response("q", [])
        self.assertEqual(len(caught.exception.result.usage_records), 2)

    def test_cancellation_records_unknown_and_closes(self):
        stream = self.respond([fixtures.delta("partial"), fixtures.stop(), metadata()])
        records = []
        gen = self.service.stream_response("q", [], usage_records=records)
        next(gen)
        gen.close()
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].cost_usd)
        self.assertEqual(records[0].status, "incomplete")
        self.assertEqual(stream.closed, 1)

    def test_records_do_not_leak_between_requests(self):
        first = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata()])
        second = self.generate([fixtures.delta("ok"), fixtures.stop()])
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertIsNone(second.input_tokens)
        self.assertEqual(first.input_tokens, 1000)

    def test_frozen_rate_snapshot_survives_configuration_change(self):
        key = ("us-east-1", self.service.model_id)
        old = MODEL_PRICING[key]
        with patch.dict(MODEL_PRICING, {key: old}):
            def events():
                yield fixtures.delta("ok")
                MODEL_PRICING[key] = ("100", "200")
                yield fixtures.stop()
                yield metadata()
            self.client.converse_stream.return_value = {"stream": fixtures.FakeStream(events())}
            records = []
            self.service.invoke_response("q", [], usage_records=records)
            self.assertEqual(records[0].cost_usd, Decimal("0.00112"))
            with self.assertRaises(FrozenInstanceError):
                records[0].cost_usd = Decimal(100)

    def test_invalid_configured_rate_is_unknown(self):
        key = ("us-east-1", self.service.model_id)
        for rate in (("NaN", "1"), ("Infinity", "1"), ("-1", "1"), ("bad", "1"), ("1",)):
            with self.subTest(rate=rate), patch.dict(MODEL_PRICING, {key: rate}):
                r = self.generate([fixtures.delta("ok"), fixtures.stop(), metadata()])
                self.assertIsNone(r.cost_usd)

    def test_unsupported_operation_rejected_before_aws(self):
        with self.assertRaises(ValueError):
            self.service.invoke_response("q", [], operation="other")
        self.client.converse_stream.assert_not_called()


class TestUsageFrontend(fixtures.OfflineCase):
    # Reuse setup/helpers without inheriting and duplicating Task 1E tests.
    def setUp(self):
        super().setUp()
        self.st = MagicMock()
        self.st.session_state = fixtures.SessionState()
        self.ui = load_frontend(self.st, self)
        self.ui._init_session_state()
        self.ui._get_or_create_service = Mock(return_value=self.service)

    def isolate_metrics_placeholder(self):
        self.st.empty.side_effect = [self.st.empty.return_value, MagicMock()]

    seed_history = fixtures.TestFrontendIntegrity.seed_history

    def chat(self, events=None):
        self.respond(events if events is not None else [fixtures.delta("ok"), fixtures.stop(), metadata()])
        self.ui._handle_user_input("q")
        return self.st.session_state.usage_ledger[-1]

    def test_chat_metadata_and_summary_are_both_counted(self):
        self.chat()
        self.respond([fixtures.delta("summary"), fixtures.stop(), metadata(2000, 200)])
        self.ui._handle_summary()
        ledger = self.st.session_state.usage_ledger
        self.assertEqual([r["operation"] for r in ledger], ["chat", "summary"])
        self.assertEqual(self.st.session_state.total_input_tokens, 3000)
        self.assertEqual(self.st.session_state.total_output_tokens, 300)
        self.assertEqual(self.ui._session_cost(), Decimal("0.00336"))
        self.assertEqual(self.st.session_state.chat_history[-1]["usage_records"], ledger[-1]["attempts"])

    def test_mixed_model_costs_never_repriced_by_selector(self):
        self.chat()
        self.service.model_id = "amazon.nova-lite-v1:0"
        self.chat()
        expected = Decimal("0.00112") + Decimal("0.000084")
        self.assertEqual(self.ui._session_cost(), expected)
        self.st.session_state.selected_model_label = "Claude 3.5 Sonnet (High Accuracy)"
        with patch.dict(MODEL_PRICING, clear=True):
            self.assertEqual(self.ui._session_cost(), expected)
        self.assertEqual(self.st.session_state.total_input_tokens, 2000)

    def test_unknown_usage_and_cost_subtotal_visible(self):
        self.chat()
        self.chat([fixtures.delta("ok"), fixtures.stop()])
        self.assertIsNone(self.ui._session_cost())
        self.assertEqual(self.ui._usage_totals()["known_cost"], Decimal("0.00112"))
        self.ui._render_usage()
        rendered = str(self.st.markdown.call_args_list) + str(self.st.caption.call_args_list)
        self.assertIn("Unknown", rendered)
        self.assertIn("Known cost subtotal", rendered)
        self.assertIn("unverified", rendered)

    def test_failure_with_usage_is_counted_without_context(self):
        request = self.chat([fixtures.delta("partial"), fixtures.stop("max_tokens"), metadata()])
        self.assertEqual(request["status"], "incomplete")
        self.assertEqual(self.ui._session_cost(), Decimal("0.00112"))
        self.assertEqual(self.st.session_state.bedrock_history, [])

    def test_failed_summary_with_usage_counted(self):
        self.seed_history()
        self.respond([fixtures.delta("partial"), fixtures.stop("max_tokens"), metadata()])
        self.ui._handle_summary()
        self.assertEqual(self.st.session_state.usage_ledger[-1]["operation"], "summary")
        self.assertEqual(self.ui._session_cost(), Decimal("0.00112"))
        self.assertEqual(len(self.st.session_state.bedrock_history), 2)

    def test_final_render_failure_does_not_discard_cost(self):
        self.isolate_metrics_placeholder()
        self.st.empty.return_value.markdown.side_effect = [None, RuntimeError("render"), None]
        request = self.chat()
        self.assertEqual(request["status"], "incomplete")
        self.assertEqual(request["attempts"][0].status, "completed")
        self.assertEqual(self.ui._session_cost(), Decimal("0.00112"))
        self.assertEqual(self.st.session_state.bedrock_history, [])

    def test_interruption_still_records_attempt(self):
        self.isolate_metrics_placeholder()
        self.st.empty.return_value.markdown.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.chat()
        ledger = self.st.session_state.usage_ledger
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["status"], "incomplete")
        self.assertIsNone(self.ui._session_cost())

    def test_initialization_failure_has_unknown_cost(self):
        self.ui._get_or_create_service.side_effect = RuntimeError("private")
        self.ui._handle_user_input("q")
        self.assertEqual(len(self.st.session_state.usage_ledger), 1)
        self.assertIsNone(self.ui._session_cost())
        self.client.converse_stream.assert_not_called()

    def test_rerender_does_not_double_count(self):
        self.chat()
        self.ui._init_session_state()
        self.ui._render_chat_history()
        self.ui._render_usage()
        self.ui._render_usage()
        self.assertEqual(len(self.st.session_state.usage_ledger), 1)
        self.assertEqual(self.st.session_state.total_input_tokens, 1000)

    def test_clear_resets_conversation_accounting(self):
        self.chat()
        self.ui._clear_conversation()
        self.assertEqual(self.st.session_state.usage_ledger, [])
        self.assertEqual(self.st.session_state.total_input_tokens, 0)
        self.assertEqual(self.ui._session_cost(), Decimal(0))

    def test_legacy_estimates_are_not_relabelled_as_actual(self):
        # Model a server-owned legacy layout, not an untrusted deletion.
        self.st.session_state.auth_session._data_scope.values.pop("usage_ledger")
        del self.st.session_state["usage_ledger"]
        self.st.session_state.total_input_tokens = 123
        self.st.session_state.total_output_tokens = 456
        self.ui._init_session_state()
        self.assertEqual(self.st.session_state.total_input_tokens, 0)
        self.assertEqual(len(self.st.session_state.usage_ledger), 1)
        self.assertIsNone(self.ui._session_cost())
        self.ui._init_session_state()
        self.assertEqual(len(self.st.session_state.usage_ledger), 1)

    def test_fallback_unknown_attempt_not_silently_zero(self):
        self.client.converse_stream.side_effect = [fixtures.denied(), {
            "stream": fixtures.FakeStream([fixtures.delta("ok"), fixtures.stop(), metadata()])
        }]
        self.ui._handle_user_input("q")
        self.assertEqual(len(self.st.session_state.usage_ledger), 1)
        self.assertIsNone(self.ui._session_cost())
        self.assertEqual(self.ui._usage_totals()["known_cost"], Decimal("0.00112"))


if __name__ == "__main__":
    unittest.main()
