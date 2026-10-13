"""Cognito authentication with authoritative, online access-token verification.

JWT decoding below is only a rejection filter. GetUser MUST succeed for the exact
token before any claims become trusted. No JWT signing implementation, credential
lookup, network call, or SDK client creation takes place at import time.
"""
import base64
import hmac
import json
import os
import re
import time
from uuid import uuid4
from dataclasses import dataclass, field

from services.aws_config import REGION, AWSConfigurationError, load_aws_config
from services.aws_retries import retry_read
from services.observability import log_event, safe_error_category


class AuthenticationError(Exception):
    """Static, display-safe failure. Never include SDK responses or credentials."""


@dataclass(frozen=True)
class AuthConfig:
    mode: str
    pool_id: str = ""
    client_id: str = ""
    max_seconds: int = 3600
    idle_seconds: int = 900

    @property
    def issuer(self):
        return f"https://cognito-idp.{REGION}.amazonaws.com/{self.pool_id}"


def load_auth_config():
    """Cognito is the default, including locally. Demo requires explicit opt-in."""
    aws = load_aws_config()
    deployed = any(os.environ.get(key) for key in (
        "AWS_EXECUTION_ENV", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI", "ECS_CONTAINER_METADATA_URI",
        "ECS_CONTAINER_METADATA_URI_V4", "AWS_LAMBDA_FUNCTION_NAME",
    ))
    if deployed and aws.mode != "task-role":
        raise AWSConfigurationError("Deployed workloads must select task-role AWS mode.")
    mode = os.environ.get("NOVAMIND_AUTH_MODE", "cognito")
    if mode not in {"cognito", "demo"}:
        raise AWSConfigurationError("NOVAMIND_AUTH_MODE must be cognito or demo.")
    if mode == "demo":
        # Container/Lambda markers prevent an accidentally omitted mode from
        # turning a deployed process into a local demo.
        if aws.mode != "local" or deployed:
            raise AWSConfigurationError("Demo authentication is restricted to local development.")
        return AuthConfig(mode)
    pool = os.environ.get("COGNITO_USER_POOL_ID", "")
    client = os.environ.get("COGNITO_APP_CLIENT_ID", "")
    if not re.fullmatch(r"us-east-1_[A-Za-z0-9]{1,55}", pool) or not re.fullmatch(r"[a-z0-9]{1,128}", client):
        raise AWSConfigurationError("Set a valid us-east-1 COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID.")
    try:
        maximum = int(os.environ.get("NOVAMIND_SESSION_MAX_SECONDS", "3600"))
        idle = int(os.environ.get("NOVAMIND_SESSION_IDLE_SECONDS", "900"))
        if not 60 <= idle <= maximum <= 86400:
            raise ValueError
    except ValueError:
        raise AWSConfigurationError("Session limits must satisfy 60 <= idle <= maximum <= 86400 seconds.") from None
    return AuthConfig(mode, pool, client, maximum, idle)


def create_cognito_client():
    """These Cognito APIs use user credentials/tokens, never IAM credentials.

    Explicit endpoint and UNSIGNED prevent SDK endpoint/profile selection from
    redirecting credentials or resolving an IAM credential chain.
    """
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    return boto3.Session(region_name=REGION).client(
        "cognito-idp", region_name=REGION,
        endpoint_url=f"https://cognito-idp.{REGION}.amazonaws.com",
        config=Config(signature_version=UNSIGNED, connect_timeout=5, read_timeout=10,
                      retries={"mode": "standard", "total_max_attempts": 1}),
    )


def _call(operation, **kwargs):
    client = None
    request_id = str(uuid4())
    started = time.perf_counter()
    status = "completed"
    error_category = None
    event_types = {
        "get_user": "cognito.identity_verify",
        "initiate_auth": "cognito.sign_in",
        "respond_to_auth_challenge": "cognito.mfa",
        "global_sign_out": "cognito.sign_out",
    }
    try:
        client = create_cognito_client()
        call = lambda: getattr(client, operation)(**kwargs)
        return retry_read(call) if operation == "get_user" else call()
    except Exception as exc:
        status = "failed"
        error_code = (exc.response.get("Error", {}).get("Code")
                      if isinstance(getattr(exc, "response", None), dict) else None)
        error_category = safe_error_category(code=error_code, exception_type=type(exc).__name__)
        raise AuthenticationError("Authentication could not be verified. Please sign in again.") from None
    finally:
        log_event(request_id=request_id, event_type=event_types.get(operation, "cognito.operation"),
                  provider="Amazon Cognito", duration_ms=(time.perf_counter() - started) * 1000,
                  status=status, error_category=error_category)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _claims(token, config, now):
    """Reject malformed/wrong-context claims; this alone NEVER authenticates."""
    try:
        if not isinstance(token, str) or len(token) > 16384:
            raise ValueError
        parts = token.split(".")
        if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
            raise ValueError
        def decode(part):
            return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)),
                              object_pairs_hook=_unique_object)
        header, claims = decode(parts[0]), decode(parts[1])
        if (header.get("alg") != "RS256" or not isinstance(header.get("kid"), str)
                or not header["kid"] or header.get("crit")
                or claims.get("iss") != config.issuer
                or claims.get("client_id") != config.client_id
                or claims.get("token_use") != "access"
                or "aws.cognito.signin.user.admin" not in claims.get("scope", "").split()
                or any(not isinstance(claims.get(key), str) or not claims[key] for key in ("sub", "username"))
                or any(type(claims.get(key)) is not int for key in ("exp", "iat", "auth_time"))
                or not 0 <= claims["auth_time"] <= claims["iat"] <= now + 30
                or not claims["iat"] < claims["exp"]
                or claims["exp"] <= now
                or ("nbf" in claims and (type(claims["nbf"]) is not int or claims["nbf"] > now))):
            raise ValueError
        return claims
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise AuthenticationError("Invalid or expired authentication. Please sign in again.") from None


def verify_access_token(token, config):
    claims = _claims(token, config, time.time())
    user = _call("get_user", AccessToken=token)
    try:
        subjects = [item["Value"] for item in user["UserAttributes"] if item["Name"] == "sub"]
        if subjects != [claims["sub"]] or user["Username"] != claims["username"]:
            raise ValueError
        verified = [item["Value"] for item in user["UserAttributes"]
                    if item["Name"] == "email_verified"]
        emails = [item["Value"] for item in user["UserAttributes"] if item["Name"] == "email"]
        claims["verified_email"] = (emails[0] if verified == ["true"] and len(emails) == 1
                                    and isinstance(emails[0], str) and
                                    re.fullmatch(r"[^\s@]{1,64}@[^\s@]{1,190}", emails[0])
                                    else "")
    except (KeyError, TypeError, ValueError):
        raise AuthenticationError("Authentication identity could not be verified.") from None
    # The network request might have crossed the expiration boundary.
    _claims(token, config, time.time())
    return claims


@dataclass(repr=False)
class AuthSession:
    config: AuthConfig
    subject: str
    username: str
    expires_at: float
    last_seen: float
    token: str = field(default="", repr=False)
    active: bool = True
    verified_email: str = ""
    _data_scope: object = field(default=None, init=False, repr=False)

    def check(self, *, online=True, touch=False):
        try:
            config = load_auth_config()
            now = time.time()
            if (not self.active or config != self.config or now >= self.expires_at
                    or now >= self.last_seen + config.idle_seconds or now < self.last_seen):
                raise AuthenticationError("Your session has expired. Please sign in again.")
            if config.mode == "cognito":
                claims = verify_access_token(self.token, config) if online else _claims(self.token, config, now)
                if claims["sub"] != self.subject or claims["username"] != self.username:
                    raise AuthenticationError("Authentication identity changed. Please sign in again.")
            # Verification latency must not revive a session past either limit.
            now = time.time()
            if not self.active or now >= self.expires_at or now >= self.last_seen + config.idle_seconds:
                raise AuthenticationError("Your session has expired. Please sign in again.")
            if touch:
                self.last_seen = now
            return self
        except (AuthenticationError, AWSConfigurationError):
            self.active = False
            raise


@dataclass(frozen=True, repr=False)
class AuthChallenge:
    config: AuthConfig
    name: str
    session: str
    username: str
    expires_at: float


def clear_session(state):
    """Invalidate outstanding service references before deleting all user data."""
    session = state.get("auth_session")
    if isinstance(session, AuthSession):
        session.active = False
        session.token = ""
    # Never close a foreign client planted in the state being discarded.
    scope = session._data_scope if isinstance(session, AuthSession) else None
    service = (scope.values.get("bedrock_service")
               if scope is not None and scope.session is session else None)
    if service is not None:
        try:
            service._client.close()
        except Exception:
            pass
    if isinstance(session, AuthSession):
        session._data_scope = None
    for key in list(state.keys()):
        del state[key]


def login(state, username, password):
    clear_session(state)
    config = load_auth_config()
    if (not isinstance(username, str) or not username.strip() or len(username) > 128
            or not isinstance(password, str) or not password or len(password) > 256):
        raise AuthenticationError("Enter your username and password.")
    now = time.time()
    if config.mode == "demo":
        from novamind.config.settings import DEMO_USERS
        expected = DEMO_USERS.get(username, "")
        if not expected or not hmac.compare_digest(expected.encode(), password.encode()):
            raise AuthenticationError("Invalid username or password.")
        session = AuthSession(config, "local:" + username, username, now + config.max_seconds, now)
    else:
        response = _call("initiate_auth", AuthFlow="USER_PASSWORD_AUTH", ClientId=config.client_id,
                         AuthParameters={"USERNAME": username.strip(), "PASSWORD": password})
        if not isinstance(response, dict):
            raise AuthenticationError("Invalid authentication response. Please sign in again.")
        if response.get("ChallengeName"):
            name = response["ChallengeName"]
            if name not in {"SMS_MFA", "SOFTWARE_TOKEN_MFA"}:
                raise AuthenticationError("Complete account setup or password recovery with your administrator before signing in.")
            challenge_session = response.get("Session")
            parameters = response.get("ChallengeParameters") or {}
            if not isinstance(parameters, dict):
                raise AuthenticationError("Invalid authentication challenge. Please sign in again.")
            canonical_user = parameters.get("USERNAME") or parameters.get("USER_ID_FOR_SRP") or username.strip()
            if (not isinstance(challenge_session, str) or not challenge_session
                    or not isinstance(canonical_user, str) or not canonical_user):
                raise AuthenticationError("Invalid authentication challenge. Please sign in again.")
            state["auth_challenge"] = AuthChallenge(config, name, challenge_session, canonical_user, now + 180)
            return
        session = _session_from_response(response, config)
    _establish(state, session)


def _session_from_response(response, config):
    try:
        token = response["AuthenticationResult"]["AccessToken"]
    except (TypeError, KeyError):
        raise AuthenticationError("Authentication was not completed. Please sign in again.") from None
    claims = verify_access_token(token, config)
    now = time.time()
    # Refresh and ID tokens are deliberately neither persisted nor used.
    return AuthSession(config, claims["sub"], claims["username"],
                       min(claims["exp"], now + config.max_seconds), now, token,
                       verified_email=claims.get("verified_email", ""))


def _establish(state, session):
    clear_session(state)
    state["auth_session"] = session
    state["data_owner"] = session.subject
    state["logged_in"] = True  # UI compatibility only; never an authorization source.
    state["login_user"] = session.username
    from services.authorization import establish_scope
    establish_scope(state, session)


def complete_mfa(state, code):
    pending = state.get("auth_challenge")
    clear_session(state)  # Challenges are single-use locally, including failures.
    config = load_auth_config()
    if not isinstance(pending, AuthChallenge) or pending.config != config or time.time() >= pending.expires_at:
        raise AuthenticationError("Authentication challenge expired. Please sign in again.")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise AuthenticationError("Enter a six-digit verification code and sign in again.")
    name, challenge_session, username = pending.name, pending.session, pending.username
    key = "SMS_MFA_CODE" if name == "SMS_MFA" else "SOFTWARE_TOKEN_MFA_CODE"
    response = _call("respond_to_auth_challenge", ClientId=config.client_id, ChallengeName=name,
                     Session=challenge_session, ChallengeResponses={"USERNAME": username, key: code})
    _establish(state, _session_from_response(response, config))


def require_session(state, *, touch=False, online=True):
    try:
        session = state.get("auth_session")
        if not isinstance(session, AuthSession):
            raise AuthenticationError("Please sign in to continue.")
        session.check(touch=touch, online=online)
        if state.get("data_owner") != session.subject:
            raise AuthenticationError("Session data does not belong to this user. Please sign in again.")
        from services.authorization import validate_scope
        validate_scope(state, session)
        return session
    except (AuthenticationError, AWSConfigurationError):
        clear_session(state)
        raise


def protect_state(state):
    """Check session ownership/time at every data boundary without repeated I/O.

    The page gate and upload callback verify online before dispatch; Bedrock also
    verifies online before each invocation. Demo sessions still require login.
    """
    return require_session(state, online=False)


def authorize_bedrock(session=None, *, online=True):
    if not isinstance(session, AuthSession):
        raise AuthenticationError("Sign in before making a Bedrock request.")
    session.check(online=online)


def logout(state):
    session = state.get("auth_session")
    token = session.token if isinstance(session, AuthSession) and session.config.mode == "cognito" else ""
    clear_session(state)  # Always local-first, even if Cognito is unavailable.
    if token:
        try:
            _call("global_sign_out", AccessToken=token)
        except AuthenticationError:
            return "Signed out locally. Cognito sign-out could not be confirmed; other sessions may remain active."
    return "Signed out."
