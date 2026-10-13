"""Offline characterization of successful BedrockService requests only."""

from tests.offline_support import demo_state
import unittest
from unittest.mock import Mock, patch

from services.bedrock_service import BedrockService


class BedrockServiceBaselineTests(unittest.TestCase):
    def setUp(self):
        # Fail even if production error handling catches a forbidden call.
        from tests.offline_support import offline_guard
        self.enterContext(offline_guard())
        # This fake has only the client operation exercised by these tests.
        self.client = Mock(spec=["converse_stream"])
        self.client.converse_stream.return_value = {
            "stream": iter([
                {"contentBlockDelta": {"delta": {"text": "Hello "}}},
                {"contentBlockDelta": {"delta": {"text": "there!"}}},
                {"messageStop": {"stopReason": "end_turn"}},
            ])
        }
        client_patch = patch(
            "services.bedrock_service.create_aws_client", return_value=self.client
        )
        self.client_factory = client_patch.start()
        self.addCleanup(client_patch.stop)

        # Explicit settings keep the tests independent of local AWS configuration.
        self.service = BedrockService(
            auth_session=demo_state()["auth_session"],
            region="us-east-1",
            model_id="amazon.nova-lite-v1:0",
            max_tokens=128,
            temperature=0.2,
            system_prompt="Test assistant.",
        )
        self.client_factory.assert_called_once()
        self.assertEqual(self.client_factory.call_args.kwargs["config"].region, "us-east-1")

    def test_text_request_uses_configured_model_and_payload(self):
        list(self.service.stream_response("  Hello  ", []))

        self.client.converse_stream.assert_called_once_with(
            modelId="amazon.nova-lite-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
            system=[{"text": "Test assistant."}],
            inferenceConfig={"maxTokens": 128, "temperature": 0.2},
        )

    def test_jpg_alias_preserves_image_bytes_in_jpeg_block(self):
        # Synthetic bytes test payload construction, not image validation.
        image_bytes = b"\xff\xd8\xfftest-image"
        list(self.service.stream_response(
            "Describe this image.",
            [],
            image_bytes=image_bytes,
            image_format=".JPG",
        ))

        self.client.converse_stream.assert_called_once_with(
            modelId="amazon.nova-lite-v1:0",
            messages=[{
                "role": "user",
                "content": [
                    {"image": {
                        "format": "jpeg",
                        "source": {"bytes": image_bytes},
                    }},
                    {"text": "Describe this image."},
                ],
            }],
            system=[{"text": "Test assistant."}],
            inferenceConfig={"maxTokens": 128, "temperature": 0.2},
        )

    def test_successful_stream_assembles_reply_and_appends_history(self):
        previous = [
            {"role": "user", "content": [{"text": "Earlier question"}]},
            {"role": "assistant", "content": [{"text": "Earlier answer"}]},
        ]
        history = list(previous)
        user_turn = {"role": "user", "content": [{"text": "Say hello"}]}

        chunks = list(self.service.stream_response("Say hello", history))

        self.assertEqual(chunks, ["Hello ", "there!"])
        self.assertEqual("".join(chunks), "Hello there!")
        self.client.converse_stream.assert_called_once_with(
            modelId="amazon.nova-lite-v1:0",
            messages=previous + [user_turn],
            system=[{"text": "Test assistant."}],
            inferenceConfig={"maxTokens": 128, "temperature": 0.2},
        )
        self.assertEqual(history, previous + [
            user_turn,
            {"role": "assistant", "content": [{"text": "Hello there!"}]},
        ])


if __name__ == "__main__":
    unittest.main()
