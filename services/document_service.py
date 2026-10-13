"""
services/document_service.py
──────────────────────────────
Handles all PDF and document file processing for the multimodal chatbot.

Responsibilities:
  - Validate uploaded document files (size, extension, MIME type, content)
  - Extract raw bytes for direct Bedrock Converse API submission
  - Validate binary document structure in a resource-limited worker
  - Extract bounded PDF previews (pypdf required; no validation bypass)
  - Return structured DocumentResult objects consumed by the frontend
  - No Streamlit imports — this layer is UI-agnostic

Design decision — Direct document understanding vs RAG:
  Nova Pro supports PDFs up to 4.5 MB directly in the Converse API.
  For single-document Q&A (the primary portfolio use case) we send document
  bytes directly to the model — no chunking, no vector store, no embeddings.
  This is simpler, cheaper, and more impressive to demo.
  RAG would be appropriate for: corpus of many documents, docs >4.5 MB,
  semantic retrieval across a knowledge base.

Document name design (Task 1B):
  The Bedrock Converse API DocumentBlock.name field has strict constraints:
    - Allowed characters: alphanumeric, single spaces, hyphens, parentheses,
      square brackets.  Underscores and periods are NOT permitted.
    - Length: 1–200 characters.
    - AWS explicitly warns this field is a prompt-injection vector and
      recommends using a neutral name.
  Therefore DocumentResult exposes two separate name properties:
    - display_name : the original sanitised filename shown in the UI.
    - api_name     : a neutral, counter-based name ("Document 1") sent to
                     Bedrock.  User-supplied filenames are never sent to the
                     model via this field.
"""

from __future__ import annotations

import json
import subprocess
import sys
import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Maximum file size Nova Pro accepts per document block (4.5 MB)
MAX_DOC_SIZE_BYTES = 4 * 1024 * 1024 + 512 * 1024   # 4.5 MB

# Supported document formats and their Bedrock format identifiers
SUPPORTED_DOC_FORMATS: dict[str, str] = {
    ".pdf":  "pdf",
    ".txt":  "txt",
    ".md":   "md",
    ".html": "html",
    ".htm":  "html",
    ".csv":  "csv",
    ".doc":  "doc",
    ".docx": "docx",
    ".xls":  "xls",
    ".xlsx": "xlsx",
}

# Friendly display labels
FORMAT_LABELS: dict[str, str] = {
    "pdf":  "PDF Document",
    "txt":  "Text File",
    "md":   "Markdown File",
    "html": "HTML File",
    "csv":  "CSV Spreadsheet",
    "doc":  "Word Document",
    "docx": "Word Document",
    "xls":  "Excel Spreadsheet",
    "xlsx": "Excel Spreadsheet",
}

# ── Bedrock document-name helpers ─────────────────────────────────────────────

# Regex for characters permitted in the Bedrock DocumentBlock.name field.
# Source: https://docs.aws.amazon.com/bedrock/latest/APIReference/
#         API_runtime_DocumentBlock.html
# Allowed: alphanumeric, single spaces, hyphens, parentheses, square brackets.
_ALLOWED_NAME_RE = re.compile(r"[^a-zA-Z0-9 \-()\[\]]")

# Maximum length of a Bedrock document name (API constraint).
_BEDROCK_NAME_MAX = 200

# Counter used to generate neutral API names that are unique within a session.
# A module-level integer is sufficient because each Streamlit session runs in
# its own Python process / thread-local memory.
_doc_api_counter: int = 0


def _next_api_name() -> str:
    """
    Return the next neutral, counter-based Bedrock document name.

    Format: "Document N"  (e.g. "Document 1", "Document 2", …)
    Always valid under the Bedrock DocumentBlock.name constraints.
    AWS recommends a neutral name to avoid prompt injection via the name field.
    """
    global _doc_api_counter
    _doc_api_counter += 1
    return f"Document {_doc_api_counter}"


def make_api_name(user_filename: str) -> str:
    """
    Convert a user-supplied filename into a Bedrock-safe document name.

    This function is intentionally NOT used for the default neutral strategy
    (see _next_api_name), but is retained as a utility for callers that want
    to derive an API name from the filename instead of using a counter.

    Rules applied:
      1. Strip the extension — Bedrock does not want it in the name.
      2. Replace every disallowed character with a space.
      3. Collapse runs of spaces into a single space and strip edges.
      4. Truncate to _BEDROCK_NAME_MAX characters.
      5. Fall back to "Document" if the result is empty.

    Args:
        user_filename: The original filename string (may include extension).

    Returns:
        A non-empty string that satisfies the Bedrock name constraints.
    """
    stem = Path(user_filename).stem            # drop extension
    cleaned = _ALLOWED_NAME_RE.sub(" ", stem)  # replace disallowed chars with space
    collapsed = re.sub(r" {2,}", " ", cleaned).strip()  # collapse multi-space
    truncated = collapsed[:_BEDROCK_NAME_MAX]
    return truncated or "Document"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DocumentResult:
    """Returned by DocumentService.process() on success."""
    file_name:     str
    file_size:     int           # bytes
    doc_format:    str           # e.g. "pdf"
    raw_bytes:     bytes         # raw file bytes — sent directly to Bedrock
    preview_text:  str           # first ~500 chars of extracted text for UI display
    page_count:    int   = 0     # number of pages (PDFs only)
    is_valid:      bool  = True
    error_message: str   = ""
    _api_name:     str   = ""    # neutral name for Bedrock API (set by DocumentService)

    @property
    def size_kb(self) -> float:
        return round(self.file_size / 1024, 1)

    @property
    def size_mb(self) -> float:
        return round(self.file_size / (1024 * 1024), 2)

    @property
    def format_label(self) -> str:
        return FORMAT_LABELS.get(self.doc_format, self.doc_format.upper())

    @property
    def display_name(self) -> str:
        """
        The original filename shown in the Streamlit UI.
        Used only for display — never sent to the Bedrock API.
        """
        return self.file_name

    @property
    def api_name(self) -> str:
        """
        A Bedrock-safe, neutral document name sent in the DocumentBlock.name
        field of the Converse API request.

        Rules (per AWS docs):
          - Alphanumeric, single spaces, hyphens, parentheses, square brackets.
          - Length 1–200 characters.
          - AWS recommends a neutral name to mitigate prompt injection.

        Returns the pre-assigned _api_name set during DocumentService.process(),
        e.g. "Document 1".  User-supplied filenames are never used here.
        """
        return self._api_name or "Document"


@dataclass
class DocumentValidationError:
    """Returned by DocumentService.process() on validation failure."""
    file_name:     str
    error_message: str
    is_valid:      bool = False


# ── Service class ─────────────────────────────────────────────────────────────

class DocumentService:
    """
    Processes and validates document uploads for Bedrock multimodal inference.

    Usage:
        svc = DocumentService()
        result = svc.process(file_bytes, file_name)
        if result.is_valid:
            # pass result.raw_bytes and result.display_name to BedrockService
    """

    def __init__(self, max_size_bytes: int = MAX_DOC_SIZE_BYTES):
        self.max_size_bytes = max_size_bytes

    # ── Public API ────────────────────────────────────────────────────────────

    def process(
        self, file_bytes: bytes, file_name: str
    ) -> DocumentResult | DocumentValidationError:
        """
        Validate and process an uploaded document file.

        Args:
            file_bytes: Raw bytes of the uploaded file
            file_name:  Original filename (used for extension detection)

        Returns:
            DocumentResult on success, DocumentValidationError on failure
        """
        file_name = file_name.strip()

        # 1. Empty file check
        if not file_bytes:
            return DocumentValidationError(
                file_name=file_name,
                error_message="File is empty. Please upload a valid document.",
            )

        # 2. File size check
        size = len(file_bytes)
        if size > min(self.max_size_bytes, MAX_DOC_SIZE_BYTES):
            mb = round(size / (1024 * 1024), 1)
            limit_mb = round(self.max_size_bytes / (1024 * 1024), 1)
            return DocumentValidationError(
                file_name=file_name,
                error_message=(
                    f"File is too large ({mb} MB). "
                    f"Maximum allowed size is {limit_mb} MB."
                ),
            )

        # 3. Extension check
        ext = Path(file_name).suffix.lower()
        if ext not in SUPPORTED_DOC_FORMATS:
            supported = ", ".join(SUPPORTED_DOC_FORMATS.keys())
            return DocumentValidationError(
                file_name=file_name,
                error_message=(
                    f"Unsupported file type '{ext}'. "
                    f"Supported formats: {supported}"
                ),
            )

        doc_format = SUPPORTED_DOC_FORMATS[ext]

        # 4. Cheap signature checks before isolated structural validation
        integrity_error = self._check_content_integrity(file_bytes, doc_format, file_name)
        if integrity_error:
            return DocumentValidationError(
                file_name=file_name, error_message=integrity_error
            )

        # 5. Extract preview text and page count
        if doc_format in ("pdf", "doc", "docx", "xls", "xlsx"):
            try:
                preview_text, page_count = self._validate_parsed_document(file_bytes, doc_format)
            except ValueError as exc:
                return DocumentValidationError(file_name, str(exc))
        else:
            preview_text, page_count = self._extract_preview(file_bytes, doc_format)

        logger.debug("Document upload validated")

        return DocumentResult(
            file_name=file_name,
            file_size=size,
            doc_format=doc_format,
            raw_bytes=file_bytes,
            preview_text=preview_text,
            page_count=page_count,
            is_valid=True,
            _api_name=_next_api_name(),   # neutral counter-based name for Bedrock
        )

    def get_supported_extensions(self) -> list[str]:
        """Return a list of supported file extensions."""
        return list(SUPPORTED_DOC_FORMATS.keys())

    def get_supported_mime_types(self) -> list[str]:
        """Return MIME types for Streamlit file_uploader type filter."""
        mime_types = []
        for ext in SUPPORTED_DOC_FORMATS:
            mime, _ = mimetypes.guess_type(f"file{ext}")
            if mime:
                mime_types.append(mime)
        # Always include PDF explicitly
        if "application/pdf" not in mime_types:
            mime_types.insert(0, "application/pdf")
        return mime_types

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_content_integrity(
        self, file_bytes: bytes, doc_format: str, file_name: str
    ) -> Optional[str]:
        """
        Perform a lightweight content integrity check.
        Returns an error string if corrupt/invalid, None if OK.
        """
        if doc_format == "pdf":
            # PDF files must start with the %PDF magic bytes
            if not file_bytes.startswith(b"%PDF"):
                return (
                    "File does not appear to be a valid PDF "
                    "(missing %PDF header). It may be corrupted."
                )
            # Must also contain %%EOF somewhere near the end
            tail = file_bytes[-1024:]
            if b"%%EOF" not in tail and b"startxref" not in tail:
                return (
                    "PDF appears to be truncated or corrupted "
                    "(missing %%EOF marker)."
                )

        elif doc_format in ("doc", "docx", "xls", "xlsx"):
            # Office Open XML and legacy Office files share magic bytes
            if not (
                file_bytes[:4] == b"PK\x03\x04"       # OOXML (docx/xlsx)
                or file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy OLE
            ):
                return (
                    f"File does not appear to be a valid "
                    f"{doc_format.upper()} document. It may be corrupted."
                )

        elif doc_format == "html":
            # HTML should contain recognisable markup
            snippet = file_bytes[:512].lower()
            if not (b"<html" in snippet or b"<!doctype" in snippet or b"<body" in snippet):
                logger.debug("HTML upload lacks standard tags; parser validation will determine acceptance")

        return None  # no error

    def _extract_preview(
        self, file_bytes: bytes, doc_format: str
    ) -> tuple[str, int]:
        """
        Extract a short preview of the document text and page count.

        Returns (preview_text, page_count).
        Binary document parsing requires its validation dependency.
        """
        preview_text = ""
        page_count   = 0

        if doc_format == "pdf":
            preview_text, page_count = self._extract_pdf_preview(file_bytes)

        elif doc_format in ("txt", "md", "csv", "html"):
            try:
                raw = file_bytes.decode("utf-8", errors="replace")
                preview_text = raw[:600].strip()
                # Approximate "pages" for text files by line count
                line_count = raw.count("\n")
                page_count = max(1, line_count // 40)
            except Exception:
                preview_text = "[Preview unavailable]"

        else:
            # docx, xlsx, doc, xls — preview not extracted without heavy deps
            preview_text = (
                f"[{doc_format.upper()} document uploaded. "
                "Preview not available — ask questions to explore the content.]"
            )

        return preview_text, page_count

    def _extract_pdf_preview(self, file_bytes: bytes) -> tuple[str, int]:
        return self._validate_parsed_document(file_bytes, "pdf")

    def _validate_parsed_document(self, file_bytes: bytes, doc_format: str) -> tuple[str, int]:
        """Bound parser wall time; never invoke a shell or extract to disk."""
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("document_parser.py")), doc_format],
                input=file_bytes, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=8, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            parsed = json.loads(result.stdout)
            if "error" in parsed:
                raise ValueError(parsed["error"])
            return parsed["preview"], parsed["pages"]
        except ValueError:
            raise
        except Exception:
            raise ValueError("File validation failed or exceeded its time limit. Upload rejected.") from None
