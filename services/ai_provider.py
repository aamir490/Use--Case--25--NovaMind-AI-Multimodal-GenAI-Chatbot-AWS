"""Factory for the configured, capability-aware AI service adapters."""
from services.bedrock_service import get_bedrock_service
from services.groq_service import GroqService
from services.provider_config import provider_for_model


def get_ai_service(*, model_id, region=None, max_tokens=None, temperature=None,
                   system_prompt=None, auth_session=None):
    provider = provider_for_model(model_id)
    if provider == "groq":
        return GroqService(model_id=model_id, max_tokens=max_tokens,
                           temperature=temperature, system_prompt=system_prompt,
                           auth_session=auth_session)
    return get_bedrock_service(region=region, model_id=model_id, max_tokens=max_tokens,
                               temperature=temperature, system_prompt=system_prompt,
                               auth_session=auth_session)
