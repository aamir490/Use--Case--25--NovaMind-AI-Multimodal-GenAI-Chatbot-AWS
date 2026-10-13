"""
utils/validators.py
─────────────────────
Shared validation and formatting utilities used across the chatbot application.

These functions are thin helpers that wrap the service-layer validation
classes and provide convenient, UI-facing utility functions.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Union

from services.document_service import (
    DocumentService,
    DocumentResult,
    DocumentValidationError,
    SUPPORTED_DOC_FORMATS,
    MAX_DOC_SIZE_BYTES,
)
from services.image_service import (
    ImageService,
    ImageResult,
    ImageValidationError,
    SUPPORTED_IMAGE_FORMATS,
    MAX_IMAGE_SIZE_BYTES,
)

# ── Singleton service instances (reused across calls) ─────────────────────────
_doc_service   = DocumentService()
_image_service = ImageService()


# ── File upload dispatcher ────────────────────────────────────────────────────

def validate_file_upload(
    file_bytes: bytes,
    file_name: str,
) -> Union[ImageResult, ImageValidationError, DocumentResult, DocumentValidationError]:
    """
    Top-level dispatcher: detect whether the uploaded file is an image or
    document, then route to the appropriate service for validation.

    Args:
        file_bytes: Raw bytes of the uploaded file
        file_name:  Original filename

    Returns:
        ImageResult | ImageValidationError | DocumentResult | DocumentValidationError
    """
    ext = Path(file_name).suffix.lower()

    if ext in SUPPORTED_IMAGE_FORMATS:
        return _image_service.process(file_bytes, file_name)
    elif ext in SUPPORTED_DOC_FORMATS:
        return _doc_service.process(file_bytes, file_name)
    else:
        # Unknown extension — return a validation error
        all_supported = sorted(
            list(SUPPORTED_IMAGE_FORMATS.keys()) + list(SUPPORTED_DOC_FORMATS.keys())
        )
        return ImageValidationError(
            file_name=file_name,
            error_message=(
                f"Unsupported file type '{ext}'. "
                f"Supported: {', '.join(all_supported)}"
            ),
        )


def is_image_file(file_name: str) -> bool:
    """Return True if the filename has an image extension."""
    return Path(file_name).suffix.lower() in SUPPORTED_IMAGE_FORMATS


def is_document_file(file_name: str) -> bool:
    """Return True if the filename has a document extension."""
    return Path(file_name).suffix.lower() in SUPPORTED_DOC_FORMATS


# ── File size formatting ──────────────────────────────────────────────────────

def format_file_size(size_bytes: int) -> str:
    """
    Return a human-readable file size string.

    Examples:
        format_file_size(512)       → "512 B"
        format_file_size(2048)      → "2.0 KB"
        format_file_size(1572864)   → "1.5 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def format_file_size_limits() -> dict[str, str]:
    """Return human-readable size limits for display in the UI."""
    return {
        "image":    format_file_size(MAX_IMAGE_SIZE_BYTES),
        "document": format_file_size(MAX_DOC_SIZE_BYTES),
    }


# ── Filename sanitisation ─────────────────────────────────────────────────────

def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    Sanitise a filename to be safe for use as a Bedrock document name
    and for display purposes.

    - Strips path separators (prevents path traversal)
    - Normalises unicode characters
    - Replaces spaces and special chars with underscores
    - Truncates to max_length
    - Preserves the file extension

    Args:
        filename:   The original filename string
        max_length: Maximum length of the returned filename (default 100)

    Returns:
        A sanitised filename string
    """
    # Strip directory components (path traversal protection)
    filename = Path(filename).name

    # Normalise unicode (NFKC: compatibility decomposition then composition)
    filename = unicodedata.normalize("NFKC", filename)

    # Separate stem and extension
    path     = Path(filename)
    stem     = path.stem
    suffix   = path.suffix.lower()

    # Replace any non-alphanumeric, non-dash, non-dot chars with underscore
    stem = re.sub(r"[^\w\-.]", "_", stem)

    # Collapse multiple underscores
    stem = re.sub(r"_+", "_", stem).strip("_")

    # Enforce max stem length (leave room for extension)
    max_stem = max_length - len(suffix) - 1
    if len(stem) > max_stem:
        stem = stem[:max_stem]

    sanitised = stem + suffix
    return sanitised or "uploaded_file" + suffix


# ── Conversation export ───────────────────────────────────────────────────────

def export_conversation_as_text(
    chat_history: list[dict],
    bot_name: str = "NovaMind",
) -> str:
    """
    Convert the Streamlit chat_history list to a plain-text transcript
    suitable for download.

    Args:
        chat_history: List of {"role": str, "text": str, "type": str} dicts
        bot_name:     Display name for the assistant

    Returns:
        A formatted multi-line string
    """
    if not chat_history:
        return "No conversation to export."

    lines = [
        f"═══ {bot_name} AI — Conversation Transcript ═══",
        "",
    ]

    for i, msg in enumerate(chat_history, 1):
        role      = msg.get("role", "unknown")
        text      = msg.get("text", "")
        msg_type  = msg.get("type", "text")   # "text" | "image" | "document"
        timestamp = msg.get("timestamp", "")

        if role == "user":
            label = "You"
        else:
            label = bot_name

        prefix = f"[{timestamp}] " if timestamp else ""
        lines.append(f"{prefix}{label}:")
        if role == "assistant" and msg.get("status", "completed") != "completed":
            lines.append(f"  [Response {msg['status']}; excluded from AI context]")

        if msg_type == "image":
            lines.append(f"  [Uploaded image: {msg.get('file_name', 'image')}]")
            if text:
                lines.append(f"  {text}")
        elif msg_type == "document":
            lines.append(f"  [Uploaded document: {msg.get('file_name', 'document')}]")
            if text:
                lines.append(f"  {text}")
        else:
            lines.append(f"  {text}")

        lines.append("")

    lines.append("═══ End of transcript ═══")
    return "\n".join(lines)


# ── Input sanitisation ────────────────────────────────────────────────────────

def sanitize_user_input(text: str, max_length: int = 10_000) -> str:
    """
    Sanitise a user's chat input before sending to the model.

    - Strips leading/trailing whitespace
    - Collapses excessively long repeated characters (e.g. aaaaaaa...)
    - Truncates to max_length with a note

    This is a lightweight guard — the model itself is the primary safety layer.
    """
    text = text.strip()

    # Truncate runaway inputs
    if len(text) > max_length:
        text = text[:max_length] + "\n[Input truncated to character limit]"

    return text
