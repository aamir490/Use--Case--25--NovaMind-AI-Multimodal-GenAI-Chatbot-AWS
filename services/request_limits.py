"""Local admission policy, not a live model catalog or exact tokenizer.

Context ceilings intentionally leave headroom below model windows. UTF-8 text
bytes plus message overhead and conservative attachment reservations are an
offline estimate; Bedrock remains authoritative for multimodal tokenization.
"""
import base64
import json
import math
from dataclasses import dataclass
from services.provider_config import SUPPORTED_GROQ_MODELS

MAX_PAYLOAD_BYTES = 20 * 1024 * 1024  # JSON including base64, with service headroom
MAX_MESSAGES = 200
MAX_IMAGES = 20
MAX_DOCUMENTS = 5
IMAGE_BYTES = 3 * 1024 * 1024 + 768 * 1024
DOCUMENT_BYTES = 4 * 1024 * 1024 + 512 * 1024
DOCUMENT_FORMATS = frozenset({"pdf", "txt", "md", "csv", "html", "doc", "docx", "xls", "xlsx"})


@dataclass(frozen=True)
class ModelPolicy:
    context_budget: int
    output_budget: int = 8192
    images: frozenset = frozenset({"jpeg", "png", "gif", "webp"})
    documents: frozenset = DOCUMENT_FORMATS


MODEL_POLICIES = {
    "amazon.nova-pro-v1:0": ModelPolicy(128000),
    "us.amazon.nova-pro-v1:0": ModelPolicy(128000),
    "amazon.nova-lite-v1:0": ModelPolicy(128000),
    "amazon.nova-micro-v1:0": ModelPolicy(128000, images=frozenset(), documents=frozenset()),
    "anthropic.claude-3-5-sonnet-20241022-v2:0": ModelPolicy(64000),
    **{model: ModelPolicy(32768, images=frozenset(), documents=frozenset())
       for model in SUPPORTED_GROQ_MODELS},
}


class RequestLimitError(ValueError):
    def __init__(self, code, message):
        self.code = "Request" + code
        super().__init__(message + " Conversation history was not changed.")


def validate_request(model_id, system_prompt, max_tokens, temperature, messages):
    """Validate all retained content, without mutating/trimming messages."""
    policy = MODEL_POLICIES.get(model_id)
    if policy is None:
        raise RequestLimitError("UnknownModel", "This model has no configured capability policy. Select a supported model.")
    if type(max_tokens) is not int or not 1 <= max_tokens <= policy.output_budget:
        raise RequestLimitError("OutputBudget", f"Output tokens must be between 1 and {policy.output_budget} for this model.")
    if type(temperature) not in (float, int) or not math.isfinite(temperature) or not 0 <= temperature <= 1:
        raise RequestLimitError("Settings", "Temperature must be between 0 and 1.")
    if not isinstance(system_prompt, str) or not isinstance(messages, list) or not messages:
        raise RequestLimitError("Structure", "Invalid system prompt or conversation structure.")
    if len(messages) > MAX_MESSAGES:
        raise RequestLimitError("MessageBudget", f"The request exceeds {MAX_MESSAGES} messages. Start a new chat explicitly to continue.")
    estimate = len(system_prompt.encode("utf-8")) + 256
    raw_size = estimate
    images = documents = 0
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"} or message["role"] not in ("user", "assistant"):
            raise RequestLimitError("Structure", "Conversation contains an unsupported message.")
        blocks = message["content"]
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 26:
            raise RequestLimitError("Structure", "Conversation contains an invalid content block count.")
        has_text = has_document = False
        estimate += 128
        for block in blocks:
            if not isinstance(block, dict) or len(block) != 1:
                raise RequestLimitError("Structure", "Conversation contains malformed content.")
            kind = next(iter(block))
            value = block[kind]
            if kind == "text":
                if not isinstance(value, str) or not value.strip():
                    raise RequestLimitError("EmptyInput", "Enter a nonblank message.")
                has_text = True
                size = len(value.encode("utf-8"))
                estimate += size
                raw_size += size
                continue
            if kind not in ("image", "document") or message["role"] != "user" or not isinstance(value, dict):
                raise RequestLimitError("Capability", "The selected model/application cannot replay this content type. Choose a compatible conversation.")
            allowed_keys = {"format", "source"} if kind == "image" else {"format", "source", "name"}
            source = value.get("source")
            if (set(value) != allowed_keys or not isinstance(source, dict) or set(source) != {"bytes"}
                    or not isinstance(source["bytes"], bytes) or not source["bytes"]):
                raise RequestLimitError("Structure", "Attachment content is missing or unsupported.")
            size = len(source["bytes"])
            formats = policy.images if kind == "image" else policy.documents
            if not isinstance(value.get("format"), str) or value["format"] not in formats:
                raise RequestLimitError("Capability", f"The selected model policy does not support this {kind} format in the request/history.")
            if size > (IMAGE_BYTES if kind == "image" else DOCUMENT_BYTES):
                raise RequestLimitError("AttachmentSize", f"A retained or new {kind} exceeds its byte limit.")
            raw_size += 4 * ((size + 2) // 3)
            if kind == "image":
                images += 1
                estimate += 8192
            else:
                documents += 1
                has_document = True
                if not isinstance(value.get("name"), str) or not 1 <= len(value["name"].strip()) <= 200:
                    raise RequestLimitError("Structure", "Document name is missing.")
                estimate += max(8192, size * 8)
        if has_document and not has_text:
            raise RequestLimitError("Structure", "Document messages require accompanying text.")
    if messages[-1]["role"] != "user":
        raise RequestLimitError("Structure", "The request must end with a user message.")
    if images > MAX_IMAGES or documents > MAX_DOCUMENTS:
        raise RequestLimitError("AttachmentCount", f"Request/history exceeds {MAX_IMAGES} images or {MAX_DOCUMENTS} documents. Start a new chat explicitly.")
    if raw_size > MAX_PAYLOAD_BYTES:
        raise RequestLimitError("PayloadBudget", "The complete request exceeds the configured payload limit. Use smaller attachments or a new chat.")
    payload = {"modelId": model_id, "messages": messages, "system": [{"text": system_prompt}],
               "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature}}
    # Standard JSON spacing/ASCII escaping conservatively matches SDK expansion.
    encoded_size = len(json.dumps(payload, default=lambda b: base64.b64encode(b).decode("ascii"), ensure_ascii=True).encode("utf-8"))
    if encoded_size > MAX_PAYLOAD_BYTES:
        raise RequestLimitError("PayloadBudget", "The serialized request exceeds the configured payload limit. Use smaller attachments or a new chat.")
    if estimate + max_tokens > policy.context_budget:
        raise RequestLimitError("ContextBudget", f"Estimated context plus reserved output exceeds the local {policy.context_budget:,}-token budget. Shorten the input, lower output tokens, or explicitly start a new chat.")
    return {"estimated_input_tokens": estimate, "payload_bytes": encoded_size}
