"""orchestration / bedrock responsibilities extracted from the Streamlit launcher."""
from services.ai_provider import get_ai_service
from services.bedrock_service import get_bedrock_service, BedrockService
from services.request_limits import validate_request, RequestLimitError
from services.aws_config import REGION, load_aws_config, safe_aws_error
from novamind.config.settings import LANGUAGE_OPTIONS, MODEL_OPTIONS, MODEL_PROVIDERS
from services.auth_service import protect_state, AuthenticationError
from services.authorization import capture_scope, check_scope, publish_data, AuthorizationError


def _get_or_create_service(state) -> BedrockService:
    """Return the cached BedrockService, recreating if model changed."""
    identity = protect_state(state)
    scope = capture_scope(state)
    model_id = MODEL_OPTIONS[state.selected_model_label]

    # Recreate if model changed or not yet created
    if state.bedrock_service is None or \
       state.bedrock_service.model_id != model_id:
        lang_instruction = LANGUAGE_OPTIONS.get(state.selected_language, "")
        full_prompt = state.system_prompt
        if lang_instruction:
            full_prompt += f"\n\n{lang_instruction}"
        factory = get_ai_service if MODEL_PROVIDERS[model_id] == "groq" else get_bedrock_service
        service = factory(
            model_id=model_id, temperature=state.temperature,
            max_tokens=state.max_tokens, system_prompt=full_prompt,
            auth_session=identity,
        )
        try:
            publish_data(state, expected=scope, bedrock_service=service)
        except AuthenticationError:
            # Cleanup must not replace an authorization denial with an SDK error.
            try:
                service._client.close()
            except Exception:
                pass
            raise
    if state.bedrock_service._auth_session is not identity:
        raise AuthorizationError("This resource is not available to this session.")
    return state.bedrock_service


def _model_context_warning(state, model_id: str) -> str | None:
    """Check retained history on model selection without changing any messages."""
    protect_state(state)
    prompt = state.system_prompt
    language = LANGUAGE_OPTIONS.get(state.selected_language, "")
    if language:
        prompt += f"\n\n{language}"
    try:
        validate_request(model_id, prompt, state.max_tokens,
                         state.temperature,
                         state.bedrock_history + [
                             {"role": "user", "content": [{"text": "Context compatibility check"}]}])
    except RequestLimitError as exc:
        return str(exc)
    return None


def _update_service_settings(state) -> None:
    """Push current sidebar settings into the existing BedrockService."""
    protect_state(state)
    svc = state.bedrock_service
    if svc:
        if svc._auth_session is not state["auth_session"]:
            raise AuthorizationError("This resource is not available to this session.")
        lang_instruction = LANGUAGE_OPTIONS.get(state.selected_language, "")
        full_prompt = state.system_prompt
        if lang_instruction:
            full_prompt += f"\n\n{lang_instruction}"
        svc.update_settings(
            temperature=state.temperature,
            max_tokens=state.max_tokens,
            system_prompt=full_prompt,
        )


def _check_aws_connection(state, *, live: bool = False) -> dict:
    """A live inference check runs only after the labelled button is pressed."""
    import time
    status = {"ok": False, "model": "", "region": REGION, "latency_ms": 0, "error": ""}
    if not live:
        status["error"] = "Live AWS check was not requested."
        return status
    identity = protect_state(state)
    scope = capture_scope(state)
    service = None
    try:
        model_id = MODEL_OPTIONS[state.selected_model_label]
        provider = MODEL_PROVIDERS[model_id]
        region = REGION
        if provider == "groq":
            service = get_ai_service(model_id=model_id, max_tokens=128, temperature=0.0,
                                     auth_session=identity)
            region = "groq-cloud"
        else:
            config = load_aws_config()
            service = get_bedrock_service(region=config.region, model_id=model_id, max_tokens=128,
                                         temperature=0.0, auth_session=identity)
            region = config.region
        start = time.monotonic()
        service.invoke_response("Reply with OK.", [],
                                authorization_check=lambda: check_scope(state, scope))
        check_scope(state, scope)
        status.update(ok=True, model=model_id, region=region,
                      latency_ms=int((time.monotonic() - start) * 1000))
    except AuthenticationError:
        raise
    except Exception as exc:
        status["error"] = safe_aws_error(exc)
    finally:
        if service is not None:
            try:
                service._client.close()
            except Exception:
                pass
    return status
