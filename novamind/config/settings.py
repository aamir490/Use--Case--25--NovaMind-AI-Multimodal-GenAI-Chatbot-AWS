"""UI choices and demo configuration; no Streamlit or AWS initialization."""
from pathlib import Path
from services.provider_config import groq_model, groq_model_label, selected_provider

ROOT = Path(__file__).resolve().parents[2]

DEMO_USERS: dict[str, str] = {
    "admin":  "novabot123",
    "aamir":  "bedrock2026",
    "demo":   "demo1234",
}

MODEL_OPTIONS: dict[str, str] = {
    "Amazon Nova Pro  (Recommended)":    "amazon.nova-pro-v1:0",
    "Amazon Nova Lite (Fast & Cheap)":   "amazon.nova-lite-v1:0",
    "Amazon Nova Micro (Text only)":     "amazon.nova-micro-v1:0",
    "Claude 3.5 Sonnet (High Accuracy)": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    groq_model_label():                     groq_model(),
}

MODEL_PROVIDERS = {model: ("groq" if model == groq_model() else "bedrock")
                   for model in MODEL_OPTIONS.values()}
DEFAULT_PROVIDER = selected_provider()

PROMPT_TEMPLATES: dict[str, str] = {
    "🤖 Default Assistant": (
        "You are NovaMind, an intelligent multimodal AI assistant powered by "
        "Amazon Nova Pro on AWS Bedrock. You can understand and discuss text, "
        "images, and documents. Be helpful, accurate, and professional."
    ),
    "🧑‍💻 Code Reviewer": (
        "You are an expert software engineer and code reviewer. Analyse code "
        "for bugs, security issues, performance problems, and style. Suggest "
        "clear improvements with examples. Be precise and technical."
    ),
    "📊 Data Analyst": (
        "You are a senior data analyst. Help interpret data, explain charts, "
        "analyse spreadsheets, and provide statistical insights. Use clear "
        "language and back every claim with reasoning."
    ),
    "📝 Document Summariser": (
        "You are an expert at summarising documents. Extract key points, "
        "decisions, and action items. Format output with bullet points. "
        "Be concise — every word must add value."
    ),
    "🎓 AWS Educator": (
        "You are a certified AWS solutions architect and educator. Explain "
        "AWS services, architectures, and best practices clearly. Use "
        "real-world examples. Cover costs, security, and trade-offs."
    ),
}

LANGUAGE_OPTIONS: dict[str, str] = {
    "English":  "Respond in English.",
    "Arabic":   "أجب باللغة العربية.",
    "French":   "Réponds en français.",
    "Spanish":  "Responde en español.",
    "German":   "Antworte auf Deutsch.",
    "Hindi":    "हिंदी में उत्तर दें।",
    "Japanese": "日本語で答えてください。",
    "Chinese":  "请用中文回答。",
}
