"""Environment-only selection for optional AI providers."""
import os
import re

SUPPORTED_GROQ_MODELS = frozenset({
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
})


def selected_provider():
    value = os.environ.get("NOVAMIND_AI_PROVIDER", "bedrock").strip().lower()
    if value not in {"bedrock", "groq"}:
        raise ValueError("NOVAMIND_AI_PROVIDER must be bedrock or groq.")
    return value


def groq_model():
    value = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    if (len(value) > 128 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}(?:/[A-Za-z0-9][A-Za-z0-9._:-]{0,63})?",
            value) or value not in SUPPORTED_GROQ_MODELS):
        raise ValueError("GROQ_MODEL must be a supported model identifier.")
    return value


def groq_model_label():
    model = groq_model()
    names = {
        "llama-3.3-70b-versatile": "Groq Cloud (Llama 3.3 70B)",
        "openai/gpt-oss-120b": "Groq Cloud (GPT-OSS 120B)",
    }
    return names[model]


def provider_for_model(model_id):
    return "groq" if model_id == groq_model() else "bedrock"
