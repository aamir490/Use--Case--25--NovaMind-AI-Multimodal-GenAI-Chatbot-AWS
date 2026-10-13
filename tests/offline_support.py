"""Reusable process-local guards, including detection of swallowed attempts."""
import os
from contextlib import ExitStack, contextmanager
from unittest.mock import patch


BLOCKED_TARGETS = (
    "socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex",
    "socket.socket.sendto", "socket.socket.sendall", "socket.socket.send",
    "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex",
    "socket.gethostbyaddr",
    "botocore.session.Session.create_client",
    "botocore.session.Session.get_credentials",
    "botocore.client.BaseClient._make_api_call",
)


def demo_state():
    """A real local login for pre-Cognito regression fixtures; no auth bypass."""
    from services.auth_service import login
    state = {}
    login(state, "demo", "demo1234")
    return state


@contextmanager
def offline_guard():
    """Cover discovery and execution; fail even when application code catches errors."""
    attempts = []

    def reject(target):
        def blocked(*args, **kwargs):
            attempts.append(target)  # Never retain credentials, addresses or payloads.
            raise AssertionError("Offline operation forbidden: " + target)
        return blocked

    with ExitStack() as stack:
        for target in BLOCKED_TARGETS:
            stack.enter_context(patch(target, side_effect=reject(target)))
        try:
            yield
        finally:
            if attempts:
                raise AssertionError("Forbidden offline operations: " + ", ".join(sorted(set(attempts))))


@contextmanager
def offline_environment():
    """Keep defaults deterministic without changing the caller's shell environment."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("AWS_", "BEDROCK_", "NOVAMIND_", "COGNITO_", "ECS_"))}
    env.update(NOVAMIND_AWS_MODE="local", NOVAMIND_AUTH_MODE="demo", AWS_PROFILE="novamind",
               AWS_DEFAULT_PROFILE="novamind", AWS_REGION="us-east-1",
               AWS_DEFAULT_REGION="us-east-1", AWS_EC2_METADATA_DISABLED="true",
               BEDROCK_MODEL_ID="amazon.nova-pro-v1:0", BEDROCK_MAX_TOKENS="2048",
               BEDROCK_TEMPERATURE="0.7", STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
    with patch.dict(os.environ, env, clear=True):
        yield
