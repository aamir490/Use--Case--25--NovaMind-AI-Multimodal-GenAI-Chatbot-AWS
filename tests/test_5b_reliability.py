"""Focused offline regressions for bounded AWS read retries and stream safety."""
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from services import auth_service
from services.aws_retries import retry_read
import test_1e_stream_integrity as stream_fixtures


class TestBoundedAwsRetries(unittest.TestCase):
    def test_transient_read_retries_with_bounded_backoff(self):
        read = Mock(side_effect=[
            ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "GetItem"),
            ClientError({"Error": {"Code": "ThrottlingException"}}, "GetItem"),
            {"Item": {"id": "safe"}},
        ])
        waits = []

        self.assertEqual(retry_read(read, sleep=waits.append), {"Item": {"id": "safe"}})
        self.assertEqual(read.call_count, 3)
        self.assertEqual(waits, [0.1, 0.2])

    def test_transient_failure_stops_after_three_attempts(self):
        failure = ClientError({"Error": {"Code": "ThrottlingException"}}, "Query")
        read = Mock(side_effect=failure)
        waits = []
        with self.assertRaises(ClientError):
            retry_read(read, sleep=waits.append)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(waits, [0.1, 0.2])

    def test_non_retryable_read_error_is_not_repeated(self):
        read = Mock(side_effect=ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetItem"))
        with self.assertRaises(ClientError):
            retry_read(read, sleep=Mock())
        read.assert_called_once()

    def test_cognito_retries_get_user_but_not_authentication_writes(self):
        client = Mock()
        client.get_user.side_effect = [EndpointConnectionError(endpoint_url="https://cognito.invalid"), {"UserAttributes": []}]
        client.initiate_auth.side_effect = EndpointConnectionError(endpoint_url="https://cognito.invalid")
        with patch.object(auth_service, "create_cognito_client", return_value=client), \
             patch("services.aws_retries.time.sleep"):
            self.assertEqual(auth_service._call("get_user", AccessToken="offline-token"), {"UserAttributes": []})
            self.assertEqual(client.get_user.call_count, 2)
            with self.assertRaises(auth_service.AuthenticationError):
                auth_service._call("initiate_auth", ClientId="offline-client")
            client.initiate_auth.assert_called_once()


class TestBedrockStreamNoReplay(stream_fixtures.OfflineCase):
    def test_timeout_after_output_closes_stream_without_replaying_request(self):
        stream = self.respond([stream_fixtures.delta("partial"),
                              ReadTimeoutError(endpoint_url="https://bedrock.invalid")])
        history = []

        with self.assertRaises(stream_fixtures.GenerationError) as caught:
            list(self.service.stream_response("question", history))

        self.assertEqual(caught.exception.result.status, "incomplete")
        self.assertEqual(history, [])
        self.client.converse_stream.assert_called_once()
        self.assertEqual(stream.closed, 1)


if __name__ == "__main__":
    unittest.main()
