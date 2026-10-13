"""Live metrics use mocked Bedrock events and never expose request content."""
from novamind.ui.live_metrics import _markup
import test_1e_stream_integrity as fixtures


class TestLiveMetrics(fixtures.OfflineCase):
    def test_stream_emits_real_latency_tokens_and_configured_cost(self):
        events = []
        self.respond([fixtures.delta("private answer"), fixtures.stop(), {
            "metadata": {"usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15}}
        }])
        result = self.service.invoke_response("private prompt", [], metrics_callback=events.append)
        self.assertEqual(result, "private answer")
        self.assertEqual(events[0]["status"], "generating")
        completed = events[-1]
        self.assertEqual((completed["input_tokens"], completed["output_tokens"]), (12, 3))
        self.assertEqual(completed["status"], "completed")
        self.assertGreaterEqual(completed["latency_ms"], completed["time_to_first_token_ms"])
        self.assertIsNotNone(completed["cost_usd"])

    def test_missing_measurements_are_labeled_and_private_content_is_omitted(self):
        panel = _markup({"provider": "Amazon Bedrock", "model": "amazon.nova-pro-v1:0",
                         "status": "idle", "latency_ms": None,
                         "time_to_first_token_ms": None, "input_tokens": None,
                         "output_tokens": None, "tokens_per_second": None,
                         "cost_usd": None}, None)
        self.assertIn("Unavailable", panel)
        self.assertIn("estimate", panel)
        self.assertNotIn("private prompt", panel)
        self.assertNotIn("private answer", panel)
