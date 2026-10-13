"""Task 5C: structured events contain operational fields, never user content."""
import json
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from services import auth_service
from services.bedrock_service import GenerationError
from tests.test_1e_stream_integrity import OfflineCase, delta, stop


class TestBedrockEvents(OfflineCase):
    def test_completed_stream_logs_allowlisted_json_without_content(self):
        self.respond([delta("PRIVATE_RESPONSE"), stop()])
        with self.assertLogs("novamind.events", level="INFO") as captured:
            list(self.service.stream_response("PRIVATE_PROMPT", []))

        # assertLogs.output adds a test-only "INFO:logger:" prefix; the
        # deployed StreamHandler writes the JSON message itself.
        messages = [record.getMessage() for record in captured.records]
        events = [json.loads(message) for message in messages]
        completed = next(event for event in events if event["status"] == "completed")
        self.assertEqual(completed["event_type"], "bedrock.request")
        self.assertEqual(completed["provider"], "Amazon Bedrock")
        self.assertEqual(completed["model"], self.service.model_id)
        self.assertGreaterEqual(completed["duration_ms"], 0)
        self.assertTrue(completed["request_id"])
        self.assertNotIn("PRIVATE_PROMPT", " ".join(messages))
        self.assertNotIn("PRIVATE_RESPONSE", " ".join(messages))

    def test_provider_error_logs_safe_category_without_exception_message(self):
        self.client.converse_stream.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "PRIVATE_AWS_DETAIL"}},
            "ConverseStream")
        with self.assertLogs("novamind.events", level="INFO") as captured:
            with self.assertRaises(GenerationError) as caught:
                list(self.service.stream_response("PRIVATE_PROMPT", []))
        messages = [record.getMessage() for record in captured.records]
        event = next(json.loads(message) for message in messages if '"status":"failed"' in message)
        self.assertEqual(event["error_category"], "throttling")
        self.assertEqual(caught.exception.result.error_code, "ThrottlingException")
        self.assertNotIn("PRIVATE_AWS_DETAIL", " ".join(messages))
        self.assertNotIn("PRIVATE_PROMPT", " ".join(messages))


class TestCognitoEvents(unittest.TestCase):
    def test_auth_operation_never_logs_token_or_error_message(self):
        client = Mock()
        client.get_user.side_effect = RuntimeError("PRIVATE_COGNITO_DETAIL")
        with patch.object(auth_service, "create_cognito_client", return_value=client):
            with self.assertLogs("novamind.events", level="INFO") as captured:
                with self.assertRaises(auth_service.AuthenticationError):
                    auth_service._call("get_user", AccessToken="PRIVATE_ACCESS_TOKEN")

        message = captured.records[0].getMessage()
        event = json.loads(message)
        self.assertEqual(event["event_type"], "cognito.identity_verify")
        self.assertEqual(event["provider"], "Amazon Cognito")
        self.assertEqual(event["status"], "failed")
        self.assertNotIn("PRIVATE_ACCESS_TOKEN", message)
        self.assertNotIn("PRIVATE_COGNITO_DETAIL", message)

