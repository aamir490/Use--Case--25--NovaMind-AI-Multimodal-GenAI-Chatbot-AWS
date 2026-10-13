"""Offline tests: fake AWS clients only, including all live-flag branches."""

from tests.frontend_support import load_frontend
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

from botocore.exceptions import ProfileNotFound, ClientError
from services import aws_config as config
import test_1e_stream_integrity as fixtures


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts/bedrock_model_access_check.py"
    spec = importlib.util.spec_from_file_location("diagnostic_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineConfigCase(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"AWS_PROFILE": "novamind", "AWS_DEFAULT_REGION": "us-east-1"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        from tests.offline_support import offline_guard
        self.enterContext(offline_guard())


class TestAWSConfiguration(OfflineConfigCase):
    def test_local_defaults_are_pinned_without_sdk_session(self):
        with patch.dict(os.environ, {}, clear=True), patch("boto3.Session") as session:
            result = config.load_aws_config()
        self.assertEqual((result.mode, result.profile, result.region), ("local", "novamind", "us-east-1"))
        session.assert_not_called()

    def test_conflicting_region_and_profile_rejected(self):
        for key, value in (("AWS_PROFILE", "default"), ("AWS_DEFAULT_PROFILE", "other"),
                           ("AWS_REGION", "us-west-2"), ("AWS_DEFAULT_REGION", "us-west-2")):
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                with self.assertRaises(config.AWSConfigurationError):
                    config.load_aws_config()
        with self.assertRaises(config.AWSConfigurationError):
            config.load_aws_config(region="us-west-2")

    def test_static_environment_credentials_fail_without_echo(self):
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            with patch.dict(os.environ, {key: "private-value"}):
                with self.assertRaises(config.AWSConfigurationError) as error:
                    config.load_aws_config()
                self.assertNotIn("private-value", str(error.exception))

    def test_local_session_always_explicit_profile(self):
        with patch("boto3.Session") as session:
            config.create_aws_session(config.load_aws_config())
        session.assert_called_once_with(profile_name="novamind", region_name="us-east-1")

    def test_missing_named_profile_never_falls_back(self):
        with patch("boto3.Session", side_effect=ProfileNotFound(profile="novamind")) as session:
            with self.assertRaises(ProfileNotFound):
                config.create_aws_client("sts")
        self.assertEqual(session.call_count, 1)

    def test_task_role_rejects_profile_selectors(self):
        with self.assertRaises(config.AWSConfigurationError):
            config.load_aws_config(mode="task-role")

    def test_task_role_credential_chain_contains_only_container_role(self):
        with patch.dict(os.environ, {"NOVAMIND_AWS_MODE": "task-role"}, clear=True):
            resolver = SimpleNamespace(providers=[SimpleNamespace(METHOD=m) for m in
                ("env", "shared-credentials-file", "custom-process", "iam-role", "container-role")])
            core = Mock()
            core.get_component.return_value = resolver
            with patch("botocore.session.get_session", return_value=core), patch("boto3.Session") as session:
                config.create_aws_session(config.load_aws_config())
            self.assertEqual([p.METHOD for p in resolver.providers], ["container-role"])
            session.assert_called_once_with(botocore_session=core, region_name="us-east-1")

    def test_task_role_missing_provider_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True), patch("botocore.session.get_session") as factory:
            factory.return_value.get_component.return_value.providers = []
            with self.assertRaises(config.AWSConfigurationError):
                config.create_aws_session(config.load_aws_config(mode="task-role"))

    def test_invalid_mode_rejected(self):
        with self.assertRaises(config.AWSConfigurationError):
            config.load_aws_config(mode="default")

    def test_client_region_timeouts_and_retry_policy(self):
        with patch("services.aws_config.create_aws_session") as session:
            config.create_aws_client("bedrock-runtime")
            config.create_aws_client("dynamodb")
            config.create_aws_client("s3")
        calls = session.return_value.client.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["bedrock-runtime", "dynamodb", "s3"])
        for call in calls:
            self.assertEqual(call.kwargs["region_name"], "us-east-1")
            self.assertEqual(call.kwargs["config"].retries["total_max_attempts"], 1)
        self.assertEqual(calls[0].kwargs["config"].read_timeout, 300)

    def test_inference_precedence(self):
        with patch.dict(os.environ, {"BEDROCK_MODEL_ID": "environment-model", "BEDROCK_MAX_TOKENS": "1024", "BEDROCK_TEMPERATURE": "0.2", "BEDROCK_SYSTEM_PROMPT": "env prompt"}):
            self.assertEqual(config.bedrock_options()["max_tokens"], 1024)
            result = config.bedrock_options(model_id="explicit", max_tokens=512, temperature=0.0, system_prompt="")
            self.assertEqual(result, {"model_id": "explicit", "max_tokens": 512, "temperature": 0.0, "system_prompt": ""})

    def test_malformed_inference_environment_safe(self):
        for key, value in (("BEDROCK_MAX_TOKENS", "private"), ("BEDROCK_TEMPERATURE", "nan")):
            with patch.dict(os.environ, {key: value}), self.assertRaises(config.AWSConfigurationError) as error:
                config.bedrock_options()
            self.assertNotIn(value, str(error.exception))

    def test_sdk_error_messages_do_not_escape(self):
        error = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "private-secret-and-arn"}}, "Test")
        self.assertNotIn("private", config.safe_aws_error(error))


class TestDiagnostics(OfflineConfigCase):
    def run_main(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.script.main(args)
        return code, output.getvalue()

    def setUp(self):
        super().setUp()
        self.script = load_script()

    def test_import_has_no_output_or_sdk_calls(self):
        output = io.StringIO()
        with patch("boto3.Session") as session, redirect_stdout(output):
            load_script()
        session.assert_not_called()
        self.assertEqual(output.getvalue(), "")

    def test_default_is_offline_and_explicitly_not_verified(self):
        with patch("boto3.Session") as session:
            code, output = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("were not checked", output)
        session.assert_not_called()

    def test_inference_requires_both_flags(self):
        with patch.object(self.script, "run_live_checks") as live:
            self.assertEqual(self.run_main(["--live-inference"])[0], 2)
        live.assert_not_called()

    def test_missing_dependency_exit_code(self):
        with patch.object(self.script.importlib.util, "find_spec", return_value=None):
            self.assertEqual(self.run_main([])[0], 1)

    def test_configuration_failure_exit_code(self):
        with patch.dict(os.environ, {"AWS_PROFILE": "default"}):
            self.assertEqual(self.run_main([])[0], 1)

    def test_live_check_flag_does_not_enable_inference(self):
        with patch.object(self.script, "run_live_checks") as live:
            self.assertEqual(self.run_main(["--live-check"])[0], 0)
        self.assertFalse(live.call_args.kwargs["inference"])

    def test_live_failure_exit_code_and_redaction(self):
        with patch.object(self.script, "run_live_checks", side_effect=RuntimeError("private-secret")):
            code, output = self.run_main(["--live-check"])
        self.assertEqual(code, 1)
        self.assertNotIn("private-secret", output)

    def test_mock_live_identity_and_catalog_clients_closed(self):
        sts, bedrock = Mock(), Mock()
        sts.get_caller_identity.return_value = {"Account": "hidden", "Arn": "hidden"}
        bedrock.list_foundation_models.return_value = {"modelSummaries": []}
        with patch("services.aws_config.create_aws_client", side_effect=[sts, bedrock]), redirect_stdout(io.StringIO()):
            self.script.run_live_checks(config.load_aws_config(), config.DEFAULT_MODEL)
        sts.close.assert_called_once()
        bedrock.close.assert_called_once()

    def test_generated_attachments_parse_and_have_valid_document_name(self):
        from PIL import Image
        from pypdf import PdfReader
        png, pdf = self.script.build_attachments()
        with Image.open(io.BytesIO(png)) as image:
            image.verify()
        self.assertEqual(len(PdfReader(io.BytesIO(pdf), strict=True).pages), 1)
        sts, bedrock, service = Mock(), Mock(), Mock()
        sts.get_caller_identity.return_value = {"Account": "hidden", "Arn": "hidden"}
        bedrock.list_foundation_models.return_value = {"modelSummaries": []}
        with patch("services.aws_config.create_aws_client", side_effect=[sts, bedrock]), patch("services.bedrock_service.BedrockService", return_value=service), redirect_stdout(io.StringIO()):
            self.script.run_live_checks(config.load_aws_config(), config.DEFAULT_MODEL, inference=True)
        self.assertEqual(service.invoke_response.call_count, 3)
        self.assertEqual(service.invoke_response.call_args.kwargs["doc_name"], "Document 1")
        service._client.close.assert_called_once()


class TestFrontendAWSConfiguration(fixtures.OfflineCase):
    def setUp(self):
        super().setUp()
        self.st = MagicMock()
        self.st.session_state = fixtures.SessionState()
        self.ui = load_frontend(self.st, self)
        self.ui._init_session_state()

    def test_connection_check_default_is_offline(self):
        with patch.object(self.ui, "get_bedrock_service") as service:
            self.assertFalse(self.ui._check_aws_connection()["ok"])
        service.assert_not_called()

    def test_connection_failure_safe_and_client_closed(self):
        service = Mock()
        service.invoke_response.side_effect = RuntimeError("private-secret")
        with patch.object(self.ui, "get_bedrock_service", return_value=service):
            result = self.ui._check_aws_connection(live=True)
        self.assertFalse(result["ok"])
        self.assertNotIn("private-secret", result["error"])
        service._client.close.assert_called_once()

    def test_ui_defaults_and_existing_selection_precedence(self):
        self.st.session_state.clear()
        from tests.offline_support import demo_state
        self.st.session_state.update(demo_state())
        with patch.dict(os.environ, {"BEDROCK_MAX_TOKENS": "1024", "BEDROCK_TEMPERATURE": "0.3", "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0"}):
            self.ui._init_session_state()
            self.assertEqual(self.st.session_state.max_tokens, 1024)
            self.assertIn("Nova Lite", self.st.session_state.selected_model_label)
            self.st.session_state.max_tokens = 4096
            self.ui._init_session_state()
            self.assertEqual(self.st.session_state.max_tokens, 4096)
