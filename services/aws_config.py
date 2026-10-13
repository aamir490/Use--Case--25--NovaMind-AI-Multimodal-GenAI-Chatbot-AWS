"""AWS configuration boundary. Reading configuration never resolves credentials.

Local: explicit novamind profile only. Deployment: explicit task-role mode,
container credential provider only. Conflicting AWS selectors fail closed.
Bedrock options: explicit arguments > environment > application defaults.
No .env file is implicitly loaded and no global boto3 session is configured.
"""
import os
import math
from dataclasses import dataclass

REGION = "us-east-1"
LOCAL_PROFILE = "novamind"
DEFAULT_MODEL = "amazon.nova-pro-v1:0"
DEFAULT_SYSTEM_PROMPT = (
    "You are NovaMind, an intelligent multimodal AI assistant powered by "
    "Amazon Nova Pro on AWS Bedrock. You can understand and discuss text, "
    "images, and documents. Be helpful, accurate, concise, and professional. "
    "When analysing images or documents, be specific and thorough. "
    "If you are unsure about something, say so clearly."
)


class AWSConfigurationError(ValueError):
    """Messages are static and safe to display; never include environment values."""


@dataclass(frozen=True)
class AWSConfig:
    mode: str
    region: str = REGION
    profile: str | None = LOCAL_PROFILE


def load_aws_config(*, region=None, mode=None):
    selected_mode = mode if mode is not None else os.environ.get("NOVAMIND_AWS_MODE", "local")
    if selected_mode not in ("local", "task-role"):
        raise AWSConfigurationError("NOVAMIND_AWS_MODE must be local or task-role.")
    if any(value != REGION for value in (region, os.environ.get("AWS_REGION"), os.environ.get("AWS_DEFAULT_REGION")) if value is not None):
        raise AWSConfigurationError("AWS region must be us-east-1; remove conflicting region settings.")
    profiles = [os.environ[key] for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE") if key in os.environ]
    if selected_mode == "local" and any(value != LOCAL_PROFILE for value in profiles):
        raise AWSConfigurationError("Local AWS profile must be novamind; remove conflicting profile settings.")
    if selected_mode == "task-role" and profiles:
        raise AWSConfigurationError("Task-role mode does not allow local AWS profile selectors.")
    if any(os.environ.get(key) for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN")):
        raise AWSConfigurationError("Remove static AWS credential environment variables; use the novamind profile or a task role.")
    return AWSConfig(selected_mode, REGION, LOCAL_PROFILE if selected_mode == "local" else None)


def create_aws_session(config):
    import boto3
    # Revalidate at the boundary; callers cannot bypass policy with a fabricated config.
    if config != load_aws_config(region=config.region, mode=config.mode):
        raise AWSConfigurationError("AWS configuration is inconsistent with the credential policy.")
    if config.mode == "local":
        return boto3.Session(profile_name=LOCAL_PROFILE, region_name=REGION)
    import botocore.session
    core = botocore.session.get_session()
    resolver = core.get_component("credential_provider")
    providers = [p for p in resolver.providers if p.METHOD == "container-role"]
    if not providers:
        raise AWSConfigurationError("The AWS SDK container-role provider is unavailable.")
    # Excludes env keys, shared/default profiles, credential_process, and IMDS.
    resolver.providers = providers
    return boto3.Session(botocore_session=core, region_name=REGION)


def create_aws_client(service_name, *, config=None):
    from botocore.config import Config
    config = config or load_aws_config()
    return create_aws_session(config).client(
        service_name, region_name=config.region,
        # Long-running Bedrock streams can take over a minute before the next
        # event; keep a finite idle-read timeout without enabling SDK replays.
        config=Config(connect_timeout=5,
                      read_timeout=300 if service_name == "bedrock-runtime" else 60,
                      retries={"mode": "standard", "total_max_attempts": 1}),
    )


def bedrock_options(*, model_id=None, max_tokens=None, temperature=None, system_prompt=None):
    try:
        options = {
            "model_id": model_id if model_id is not None else os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL),
            "max_tokens": max_tokens if max_tokens is not None else int(os.environ.get("BEDROCK_MAX_TOKENS", "2048")),
            "temperature": temperature if temperature is not None else float(os.environ.get("BEDROCK_TEMPERATURE", "0.7")),
            "system_prompt": system_prompt if system_prompt is not None else os.environ.get("BEDROCK_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        }
        if (type(options["max_tokens"]) is not int or not 1 <= options["max_tokens"] <= 8192
                or type(options["temperature"]) not in (int, float)
                or not math.isfinite(options["temperature"]) or not 0 <= options["temperature"] <= 1
                or not isinstance(options["system_prompt"], str)
                or not isinstance(options["model_id"], str) or not options["model_id"].strip()):
            raise AWSConfigurationError("Bedrock settings require a model, text prompt, output tokens from 1 to 8192, and temperature from 0 to 1.")
        return options
    except AWSConfigurationError:
        raise
    except (ValueError, TypeError):
        raise AWSConfigurationError("Bedrock inference settings must contain valid numeric values.") from None


def safe_aws_error(exc):
    """Do not echo SDK messages, account IDs, ARNs, paths, or service responses."""
    if isinstance(exc, AWSConfigurationError):
        return str(exc)
    name = type(exc).__name__
    if name in {"ProfileNotFound", "NoCredentialsError", "PartialCredentialsError", "CredentialRetrievalError"}:
        return "AWS credentials are unavailable. Check the configured profile or task role."
    if name in {"EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"}:
        return "AWS connection failed or timed out. Check network access and retry."
    return "AWS check failed. Verify credentials, region, IAM permissions, and model access."
