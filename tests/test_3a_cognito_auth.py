"""Task 3A: all AWS responses are mocked; never contact Cognito or Bedrock."""
import base64
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError
from services import auth_service as auth
from services.aws_config import AWSConfigurationError
from services.bedrock_service import BedrockService
from tests.offline_support import offline_guard


NOW = 100000
ENV = {"NOVAMIND_AWS_MODE": "task-role", "NOVAMIND_AUTH_MODE": "cognito",
       "COGNITO_USER_POOL_ID": "us-east-1_example", "COGNITO_APP_CLIENT_ID": "client123",
       "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false", "AWS_EC2_METADATA_DISABLED": "true"}


def token(**overrides):
    """Synthetic JWT is NOT signed; only our mocked Cognito can accept it."""
    claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
              "client_id": "client123", "token_use": "access", "sub": "subject-1",
              "username": "alice", "exp": NOW + 600, "iat": NOW - 10,
              "auth_time": NOW - 10, "scope": "aws.cognito.signin.user.admin"}
    claims.update(overrides)
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return encode({"alg": "RS256", "kid": "mock-key"}) + "." + encode(claims) + ".c2lnbmF0dXJl"


class State(dict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value


class TestCognitoAuth(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_guard())
        self.enterContext(patch.dict(os.environ, ENV, clear=True))
        self.clock = self.enterContext(patch.object(auth.time, "time", return_value=NOW))
        self.client = Mock(spec=["initiate_auth", "get_user", "global_sign_out",
                                 "respond_to_auth_challenge", "close"])
        self.factory = self.enterContext(patch.object(auth, "create_cognito_client", return_value=self.client))
        self.client.initiate_auth.return_value = {"AuthenticationResult": {
            "AccessToken": token(), "IdToken": "discard-id", "RefreshToken": "discard-refresh"}}
        self.client.get_user.return_value = {
            "Username": "alice", "UserAttributes": [{"Name": "sub", "Value": "subject-1"}]}
        self.state = State()

    def sign_in(self):
        auth.login(self.state, "alice", "private-password")
        return self.state["auth_session"]

    def test_config_is_passive_and_defaults_to_cognito(self):
        del os.environ["NOVAMIND_AUTH_MODE"]
        self.assertEqual(auth.load_auth_config().mode, "cognito")
        self.factory.assert_not_called()

    def test_missing_wrong_region_and_invalid_client_fail_closed(self):
        for key, value in (("COGNITO_USER_POOL_ID", ""), ("COGNITO_USER_POOL_ID", "us-west-2_pool"),
                           ("COGNITO_APP_CLIENT_ID", "https://bad"), ("NOVAMIND_AUTH_MODE", "disabled"),
                           ("NOVAMIND_SESSION_IDLE_SECONDS", "0"), ("NOVAMIND_SESSION_MAX_SECONDS", "nan")):
            with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}):
                with self.assertRaises(AWSConfigurationError):
                    auth.load_auth_config()
        self.factory.assert_not_called()

    def test_demo_forbidden_in_deployment(self):
        with patch.dict(os.environ, {"NOVAMIND_AUTH_MODE": "demo"}):
            with self.assertRaises(AWSConfigurationError):
                auth.load_auth_config()
        with patch.dict(os.environ, {"NOVAMIND_AUTH_MODE": "demo", "NOVAMIND_AWS_MODE": "local",
                                    "AWS_EXECUTION_ENV": "AWS_ECS_FARGATE"}):
            with self.assertRaises(AWSConfigurationError):
                auth.load_auth_config()
        self.factory.assert_not_called()

    def test_demo_login_requires_explicit_local_mode_and_never_calls_cognito(self):
        with patch.dict(os.environ, {"NOVAMIND_AUTH_MODE": "demo", "NOVAMIND_AWS_MODE": "local"}):
            auth.login(self.state, "demo", "demo1234")
            auth.require_session(self.state)
            self.assertEqual(self.state["data_owner"], "local:demo")
            with self.assertRaises(auth.AuthenticationError):
                auth.authorize_bedrock()
            self.assertEqual(auth.logout(self.state), "Signed out.")
        self.factory.assert_not_called()

    def test_successful_login_verifies_exact_token_and_discards_secrets(self):
        self.state.update(chat_history=["old-user"], pending_document=b"old-upload")
        session = self.sign_in()
        self.client.initiate_auth.assert_called_once_with(
            AuthFlow="USER_PASSWORD_AUTH", ClientId="client123",
            AuthParameters={"USERNAME": "alice", "PASSWORD": "private-password"})
        self.client.get_user.assert_called_once_with(AccessToken=token())
        self.assertEqual((session.subject, session.username), ("subject-1", "alice"))
        self.assertEqual(session.expires_at, NOW + 600)
        self.assertNotIn("chat_history", self.state)
        self.assertNotIn("pending_document", self.state)
        for secret in ("discard-id", "discard-refresh", "private-password", token()):
            self.assertNotIn(secret, repr(self.state))
        self.assertEqual(self.client.close.call_count, 2)

    def test_demo_credentials_in_cognito_mode_still_require_cognito(self):
        self.client.initiate_auth.side_effect = RuntimeError("secret SDK detail")
        with self.assertRaises(auth.AuthenticationError) as caught:
            auth.login(self.state, "demo", "demo1234")
        self.assertEqual(self.state, {})
        self.assertNotIn("secret", str(caught.exception))

    def test_wrong_claims_rejected_before_aws(self):
        changes = [{"iss": "https://attacker.invalid"}, {"client_id": "another-client"},
                   {"token_use": "id"}, {"exp": NOW}, {"exp": True}, {"iat": NOW + 31},
                   {"auth_time": NOW + 60}, {"nbf": NOW + 1}, {"scope": "openid"},
                   {"sub": ""}, {"username": []}, {"iat": "99990"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(auth.AuthenticationError):
                auth.verify_access_token(token(**change), auth.load_auth_config())
        self.client.get_user.assert_not_called()

    def test_malformed_and_unsigned_tokens_rejected(self):
        none_header = base64.urlsafe_b64encode(b'{"alg":"none","kid":"x"}').decode().rstrip("=")
        duplicate = base64.urlsafe_b64encode(b'{"alg":"RS256","alg":"none","kid":"x"}').decode().rstrip("=")
        for value in (None, "", "opaque", "a.b.c", "x" * 16385,
                      none_header + "." + token().split(".")[1] + ".x",
                      duplicate + "." + token().split(".")[1] + ".x"):
            with self.subTest(value=str(value)[:30]), self.assertRaises(auth.AuthenticationError):
                auth.verify_access_token(value, auth.load_auth_config())
        self.client.get_user.assert_not_called()

    def test_plausible_claims_are_not_proof_of_a_valid_signature(self):
        self.client.get_user.side_effect = ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "bad signature PRIVATE"}}, "GetUser")
        with self.assertRaises(auth.AuthenticationError) as caught:
            self.sign_in()
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertNotIn("auth_session", self.state)

    def test_verified_user_must_match_token_subject_and_username(self):
        for response in ({"Username": "other", "UserAttributes": [{"Name": "sub", "Value": "subject-1"}]},
                         {"Username": "alice", "UserAttributes": [{"Name": "sub", "Value": "other"}]},
                         {"Username": "alice", "UserAttributes": []}):
            self.client.get_user.return_value = response
            with self.assertRaises(auth.AuthenticationError):
                self.sign_in()
            self.assertEqual(self.state, {})

    def test_network_timeout_fails_closed_and_closes_client(self):
        self.client.get_user.side_effect = TimeoutError("private token")
        with self.assertRaises(auth.AuthenticationError) as caught:
            self.sign_in()
        self.assertEqual(self.state, {})
        self.assertNotIn("private token", str(caught.exception))
        self.assertEqual(self.client.close.call_count, 2)

    def test_token_expiring_during_verification_is_rejected(self):
        def expire(**kwargs):
            self.clock.return_value = NOW + 600
            return {"Username": "alice", "UserAttributes": [{"Name": "sub", "Value": "subject-1"}]}
        self.client.get_user.side_effect = expire
        with self.assertRaises(auth.AuthenticationError):
            self.sign_in()

    def test_revoked_session_clears_all_protected_state(self):
        session = self.sign_in()
        self.state.update(chat_history=["private"], usage_ledger=[1], pending_image=b"private")
        self.client.get_user.side_effect = RuntimeError("revoked")
        with self.assertRaises(auth.AuthenticationError):
            auth.require_session(self.state)
        self.assertEqual(self.state, {})
        self.assertFalse(session.active)
        self.assertEqual(session.token, "")

    def test_expiration_and_idle_timeout_clear_state_without_aws(self):
        for advance, settings in ((600, {}), (60, {"NOVAMIND_SESSION_IDLE_SECONDS": "60"}),
                                  (60, {"NOVAMIND_SESSION_IDLE_SECONDS": "60", "NOVAMIND_SESSION_MAX_SECONDS": "60"})):
            with self.subTest(advance=advance, settings=settings), patch.dict(os.environ, settings):
                self.clock.return_value = NOW
                self.sign_in()
                calls = self.client.get_user.call_count
                self.clock.return_value = NOW + advance
                with self.assertRaises(auth.AuthenticationError):
                    auth.require_session(self.state)
                self.assertEqual(self.state, {})
                self.assertEqual(self.client.get_user.call_count, calls)

    def test_watchdog_style_checks_do_not_extend_idle_time(self):
        session = self.sign_in()
        self.clock.return_value = NOW + 10
        auth.require_session(self.state)
        self.assertEqual(session.last_seen, NOW)
        auth.require_session(self.state, touch=True)
        self.assertEqual(session.last_seen, NOW + 10)

    def test_verification_latency_cannot_revive_idle_session(self):
        with patch.dict(os.environ, {"NOVAMIND_SESSION_IDLE_SECONDS": "60"}):
            self.sign_in()
            self.clock.return_value = NOW + 59
            response = self.client.get_user.return_value
            def slow_verification(**kwargs):
                self.clock.return_value = NOW + 60
                return response
            self.client.get_user.side_effect = slow_verification
            with self.assertRaises(auth.AuthenticationError):
                auth.require_session(self.state, touch=True)
        self.assertEqual(self.state, {})

    def test_owner_mismatch_and_configuration_change_invalidate(self):
        self.sign_in()
        self.state["data_owner"] = "another-user"
        with self.assertRaises(auth.AuthenticationError):
            auth.protect_state(self.state)
        self.assertEqual(self.state, {})
        self.sign_in()
        with patch.dict(os.environ, {"COGNITO_APP_CLIENT_ID": "different"}):
            with self.assertRaises(auth.AuthenticationError):
                auth.require_session(self.state)
        self.assertEqual(self.state, {})

    def test_logout_always_clears_and_invalidates_cached_service(self):
        session = self.sign_in()
        from services.authorization import publish_data
        service = Mock(_auth_session=session)
        publish_data(self.state, bedrock_service=service, chat_history=["private"])
        self.state.update(login_password_input="password", attachment_upload_0=b"upload")
        self.client.global_sign_out.side_effect = TimeoutError("private-detail")
        notice = auth.logout(self.state)
        self.client.global_sign_out.assert_called_once_with(AccessToken=token())
        self.assertEqual(self.state, {})
        service._client.close.assert_called_once()
        self.assertFalse(session.active)
        self.assertEqual(session.token, "")
        self.assertIn("could not be confirmed", notice)
        self.assertNotIn("private-detail", notice)

    def test_logout_success_calls_global_sign_out(self):
        self.sign_in()
        self.assertEqual(auth.logout(self.state), "Signed out.")
        self.client.global_sign_out.assert_called_once_with(AccessToken=token())
        self.assertEqual(self.state, {})

    def test_mfa_is_not_authenticated_until_verified(self):
        for name, key in (("SMS_MFA", "SMS_MFA_CODE"), ("SOFTWARE_TOKEN_MFA", "SOFTWARE_TOKEN_MFA_CODE")):
            with self.subTest(name=name):
                self.client.initiate_auth.return_value = {"ChallengeName": name, "Session": "challenge-secret",
                                                         "ChallengeParameters": {"USERNAME": "alice"}}
                self.client.respond_to_auth_challenge.return_value = {"AuthenticationResult": {"AccessToken": token()}}
                auth.login(self.state, "alias", "password")
                self.assertNotIn("auth_session", self.state)
                auth.complete_mfa(self.state, "123456")
                self.assertEqual(self.state["auth_session"].subject, "subject-1")
                self.client.respond_to_auth_challenge.assert_called_with(
                    ClientId="client123", ChallengeName=name, Session="challenge-secret",
                    ChallengeResponses={"USERNAME": "alice", key: "123456"})
                self.assertNotIn("auth_challenge", self.state)

    def test_expired_mfa_and_unsupported_challenges_fail_closed(self):
        self.client.initiate_auth.return_value = {"ChallengeName": "SMS_MFA", "Session": "pending"}
        auth.login(self.state, "alice", "password")
        self.clock.return_value = NOW + 180
        with self.assertRaises(auth.AuthenticationError):
            auth.complete_mfa(self.state, "123456")
        self.client.respond_to_auth_challenge.assert_not_called()
        self.assertEqual(self.state, {})
        self.client.initiate_auth.return_value = {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "pending"}
        with self.assertRaises(auth.AuthenticationError):
            auth.login(self.state, "alice", "password")
        self.assertEqual(self.state, {})

    def test_failed_mfa_is_single_use_and_never_grants_access(self):
        self.client.initiate_auth.return_value = {"ChallengeName": "SMS_MFA", "Session": "pending-secret"}
        auth.login(self.state, "alice", "password")
        self.assertNotIn("pending-secret", repr(self.state))
        self.client.respond_to_auth_challenge.side_effect = RuntimeError("private-code")
        with self.assertRaises(auth.AuthenticationError):
            auth.complete_mfa(self.state, "123456")
        self.assertEqual(self.state, {})
        with self.assertRaises(auth.AuthenticationError):
            auth.complete_mfa(self.state, "123456")
        self.client.respond_to_auth_challenge.assert_called_once()

    def test_unauthenticated_service_never_creates_bedrock_client(self):
        with patch("services.bedrock_service.create_aws_client") as factory:
            with self.assertRaises(auth.AuthenticationError):
                BedrockService()
        factory.assert_not_called()

    def test_service_blocks_cached_session_after_logout(self):
        session = self.sign_in()
        client = Mock()
        with patch("services.bedrock_service.create_aws_client", return_value=client):
            service = BedrockService(auth_session=session)
        auth.logout(self.state)
        for invoke in (lambda: list(service.stream_response("q", [])), lambda: service.invoke_response("q", [])):
            with self.assertRaises(auth.AuthenticationError):
                invoke()
        client.converse_stream.assert_not_called()

    def test_expiration_during_stream_closes_without_committing_history(self):
        session = self.sign_in()
        client, stream = Mock(), MagicMock()
        def events():
            yield {"contentBlockDelta": {"delta": {"text": "partial"}}}
            self.clock.return_value = NOW + 600
            yield {"messageStop": {"stopReason": "end_turn"}}
        stream.__iter__.side_effect = events
        client.converse_stream.return_value = {"stream": stream}
        with patch("services.bedrock_service.create_aws_client", return_value=client):
            service = BedrockService(auth_session=session)
        history = []
        chunks = service.stream_response("q", history)
        self.assertEqual(next(chunks), "partial")
        with self.assertRaises(auth.AuthenticationError):
            next(chunks)
        self.assertEqual(history, [])
        stream.close.assert_called_once()

    def test_revocation_before_fallback_prevents_second_invocation(self):
        session = self.sign_in()
        client = Mock()
        def deny(**kwargs):
            self.client.get_user.side_effect = RuntimeError("revoked")
            raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "ConverseStream")
        client.converse_stream.side_effect = deny
        with patch("services.bedrock_service.create_aws_client", return_value=client):
            service = BedrockService(auth_session=session)
        with self.assertRaises(auth.AuthenticationError):
            list(service.stream_response("q", []))
        client.converse_stream.assert_called_once()

    def test_protected_data_and_upload_callbacks_reject_boolean_only(self):
        from novamind.domain import session, usage
        from novamind.orchestration import uploads, bedrock
        actions = [session._init_session_state, usage._usage_totals,
                   lambda state: uploads._handle_file_upload(state, Mock()),
                   lambda state: uploads._on_upload_changed(state, "attachment_upload_0"),
                   bedrock._get_or_create_service,
                   lambda state: bedrock._check_aws_connection(state, live=True)]
        for action in actions:
            state = State(logged_in=True, login_user="admin", chat_history=["private"])
            with self.subTest(action=action), self.assertRaises(auth.AuthenticationError):
                action(state)
            self.assertEqual(state, {})
        self.factory.assert_not_called()

    def test_two_sessions_and_second_login_do_not_share_data(self):
        first = self.sign_in()
        other = State()
        auth.login(other, "alice", "password")
        self.state["chat_history"] = ["private"]
        auth.logout(other)
        self.assertTrue(first.active)
        self.assertEqual(self.state["chat_history"], ["private"])
        self.sign_in()
        self.assertFalse(first.active)
        self.assertNotIn("chat_history", self.state)


class TestCognitoClientBoundary(unittest.TestCase):
    def test_unsigned_client_has_fixed_tls_endpoint_and_no_iam_credentials(self):
        from botocore import UNSIGNED
        with offline_guard(), patch("boto3.Session") as factory:
            auth.create_cognito_client()
        factory.assert_called_once_with(region_name="us-east-1")
        options = factory.return_value.client.call_args.kwargs
        self.assertEqual(options["endpoint_url"], "https://cognito-idp.us-east-1.amazonaws.com")
        self.assertEqual(options["config"].signature_version, UNSIGNED)
        self.assertEqual(options["config"].retries["total_max_attempts"], 1)


class TestCognitoFrontend(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_guard())
        self.enterContext(patch.dict(os.environ, ENV, clear=True))
        self.client = Mock()
        self.enterContext(patch.object(auth, "create_cognito_client", return_value=self.client))
        from streamlit.testing.v1 import AppTest
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "mod_chatbot_frontend.py"),
                                    default_timeout=15)

    def test_forged_boolean_does_not_expose_chat_or_demo_credentials(self):
        self.app.session_state["logged_in"] = True
        self.app.session_state["login_user"] = "admin"
        self.app.session_state["chat_history"] = [{"text": "PRIVATE_HISTORY"}]
        self.app.run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(len(self.app.chat_input), 0)
        self.assertEqual(len(self.app.file_uploader), 0)
        rendered = " ".join(item.value for item in self.app.markdown)
        self.assertNotIn("PRIVATE_HISTORY", rendered)
        self.assertNotIn("demo1234", rendered)
        self.client.initiate_auth.assert_not_called()

    def test_cognito_form_login_and_logout_clear_password_and_private_widgets(self):
        import time
        now = int(time.time())
        self.client.initiate_auth.return_value = {"AuthenticationResult": {
            "AccessToken": token(exp=now + 600, iat=now, auth_time=now)}}
        self.client.get_user.return_value = {
            "Username": "alice", "UserAttributes": [{"Name": "sub", "Value": "subject-1"}]}
        self.app.run()
        self.app.text_input(key="login_username_input").set_value("alice")
        self.app.text_input(key="login_password_input").set_value("private-password")
        next(button for button in self.app.button if button.label == "🔐  Sign In").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(len(self.app.chat_input), 1)
        self.assertNotIn("login_password_input", self.app.session_state)
        next(button for button in self.app.button if button.label == "🚪 Sign Out").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(len(self.app.chat_input), 0)
        self.assertNotIn("auth_session", self.app.session_state)
        self.client.global_sign_out.assert_called_once()

    def test_private_export_and_preview_do_not_publish_media_urls(self):
        import time
        now = int(time.time())
        self.client.initiate_auth.return_value = {"AuthenticationResult": {
            "AccessToken": token(exp=now + 600, iat=now, auth_time=now)}}
        self.client.get_user.return_value = {
            "Username": "alice", "UserAttributes": [{"Name": "sub", "Value": "subject-1"}]}
        state = State()
        auth.login(state, "alice", "password")
        for key, value in state.items():
            self.app.session_state[key] = value
        self.app.run()
        self.app.session_state["chat_history"][:] = [{"role": "user", "text": "PRIVATE_TRANSCRIPT",
                                                  "type": "image", "file_name": "<private>.png",
                                                  "thumbnail_bytes": b"mock-thumbnail"}]
        self.app.run()
        next(button for button in self.app.button if button.label == "📋 Export transcript").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertTrue(any("PRIVATE_TRANSCRIPT" in item.value for item in self.app.code))
        self.assertEqual(len(self.app.get("download_button")), 0)
        self.assertTrue(any("data:image/png;base64," in item.value for item in self.app.markdown))
        self.assertTrue(any("&lt;private&gt;.png" in item.value for item in self.app.markdown))
