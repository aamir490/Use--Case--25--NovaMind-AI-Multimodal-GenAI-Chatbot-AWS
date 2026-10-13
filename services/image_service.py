"""
services/image_service.py
───────────────────────────
Handles all image file processing for the multimodal chatbot.

Responsibilities:
  - Validate uploaded image files (size, extension, MIME type, dimensions)
  - Normalise image format (convert JPEG aliases, handle transparency)
  - Generate thumbnails for UI preview
  - Return raw bytes for direct Bedrock Converse API image blocks
  - Return structured ImageResult objects consumed by the frontend
  - No Streamlit imports — this layer is UI-agnostic

Supported formats: JPEG, PNG, GIF, WebP
  (Amazon Nova Pro Converse API image block supported formats)

Bedrock Converse API image limits (Task 1C — verified from AWS docs):
  - Per-image size:   3.75 MB  (source: API_runtime_Message.html)
  - Max dimension:    8,000 px per side
  - Total payload:    25 MB  (not enforced here — single-image use case)
"""

from __future__ import annotations

import io
import logging
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Maximum image size per image block enforced by Bedrock Converse API.
# Source: https://docs.aws.amazon.com/bedrock/latest/APIReference/
#         API_runtime_Message.html — "Each image's size … must be no more than 3.75 MB"
# Previous value was 5 MB, which allowed files that Bedrock would reject.
MAX_IMAGE_SIZE_BYTES = 3 * 1024 * 1024 + 768 * 1024   # 3.75 MB exactly

# Maximum pixel dimension per side enforced by Bedrock Converse API.
# Source: same reference — "height, and width must be no more than … 8000 px"
MAX_IMAGE_DIMENSION = 8_000   # pixels
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_FRAMES = 32
MAX_TOTAL_FRAME_PIXELS = 32_000_000

# Supported image extensions → Bedrock format identifiers
SUPPORTED_IMAGE_FORMATS: dict[str, str] = {
    ".jpg":  "jpeg",
    ".jpeg": "jpeg",
    ".png":  "png",
    ".gif":  "gif",
    ".webp": "webp",
}

# Human-readable labels
FORMAT_LABELS: dict[str, str] = {
    "jpeg": "JPEG Image",
    "png":  "PNG Image",
    "gif":  "GIF Image",
    "webp": "WebP Image",
}

# Maximum dimension for thumbnail generation (pixels)
THUMBNAIL_MAX_SIZE = (400, 400)

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ImageResult:
    """Returned by ImageService.process() on success."""
    file_name:     str
    file_size:     int           # bytes
    img_format:    str           # e.g. "jpeg" — the Bedrock format identifier
    raw_bytes:     bytes         # raw image bytes — sent directly to Bedrock
    thumbnail_bytes: Optional[bytes]  # compressed preview for Streamlit st.image()
    width:         int   = 0
    height:        int   = 0
    is_valid:      bool  = True
    error_message: str   = ""

    @property
    def size_kb(self) -> float:
        return round(self.file_size / 1024, 1)

    @property
    def dimensions(self) -> str:
        if self.width and self.height:
            return f"{self.width} × {self.height} px"
        return "Unknown dimensions"

    @property
    def format_label(self) -> str:
        return FORMAT_LABELS.get(self.img_format, self.img_format.upper())


@dataclass
class ImageValidationError:
    """Returned by ImageService.process() on validation failure."""
    file_name:     str
    error_message: str
    is_valid:      bool = False


# ── Service class ─────────────────────────────────────────────────────────────

class ImageService:
    """
    Processes and validates image uploads for Bedrock multimodal inference.

    Usage:
        svc = ImageService()
        result = svc.process(file_bytes, file_name)
        if result.is_valid:
            # pass result.raw_bytes and result.img_format to BedrockService
            # use result.thumbnail_bytes in st.image() for preview
    """

    def __init__(self, max_size_bytes: int = MAX_IMAGE_SIZE_BYTES):
        self.max_size_bytes = max_size_bytes

    # ── Public API ────────────────────────────────────────────────────────────

    def process(
        self, file_bytes: bytes, file_name: str
    ) -> ImageResult | ImageValidationError:
        """
        Validate and process an uploaded image file.

        Args:
            file_bytes: Raw bytes of the uploaded file
            file_name:  Original filename (used for extension detection)

        Returns:
            ImageResult on success, ImageValidationError on failure
        """
        file_name = file_name.strip()

        # 1. Empty file check
        if not file_bytes:
            return ImageValidationError(
                file_name=file_name,
                error_message="File is empty. Please upload a valid image.",
            )

        # 2. File size check  (Bedrock limit: 3.75 MB per image block)
        size = len(file_bytes)
        if size > min(self.max_size_bytes, MAX_IMAGE_SIZE_BYTES):
            mb    = round(size / (1024 * 1024), 1)
            limit = round(self.max_size_bytes / (1024 * 1024), 2)
            return ImageValidationError(
                file_name=file_name,
                error_message=(
                    f"Image is too large ({mb} MB). "
                    f"Maximum allowed size is {limit} MB "
                    f"(Amazon Bedrock Converse API limit)."
                ),
            )

        # 3. Extension check
        ext = Path(file_name).suffix.lower()
        if ext not in SUPPORTED_IMAGE_FORMATS:
            supported = ", ".join(SUPPORTED_IMAGE_FORMATS.keys())
            return ImageValidationError(
                file_name=file_name,
                error_message=(
                    f"Unsupported image format '{ext}'. "
                    f"Supported formats: {supported}"
                ),
            )

        img_format = SUPPORTED_IMAGE_FORMATS[ext]

        # 4. Magic bytes / content integrity check
        integrity_error = self._check_magic_bytes(file_bytes, img_format, file_name)
        if integrity_error:
            return ImageValidationError(
                file_name=file_name, error_message=integrity_error
            )

        # 5. Open with Pillow for full decode, dimensions, and thumbnail.
        #    _process_with_pillow now returns a 5-tuple; the fifth element is
        #    an optional error string set when Pillow fails to fully decode
        #    the image (e.g. truncated JPEG that passed magic-byte check).
        width, height, raw_bytes_final, thumbnail_bytes, pillow_error = (
            self._process_with_pillow(file_bytes, img_format)
        )

        # 5a. Reject files that Pillow cannot fully decode.
        #     A file with a valid header but truncated/corrupt body would
        #     previously pass validation and cause a Bedrock ValidationException.
        if pillow_error:
            return ImageValidationError(
                file_name=file_name,
                error_message=pillow_error,
            )

        # 5b. Dimension check  (Bedrock limit: 8,000 px per side)
        if not (0 < width <= MAX_IMAGE_DIMENSION and 0 < height <= MAX_IMAGE_DIMENSION) or width * height > MAX_IMAGE_PIXELS:
            return ImageValidationError(
                file_name=file_name,
                error_message=(
                    f"Image dimensions ({width} × {height} px) exceed the "
                    f"Amazon Bedrock limit of {MAX_IMAGE_DIMENSION} px per side. "
                    f"Please resize the image before uploading."
                ),
            )

        if not raw_bytes_final or len(raw_bytes_final) > min(self.max_size_bytes, MAX_IMAGE_SIZE_BYTES):
            return ImageValidationError(file_name, "Processed image exceeds the allowed size or is empty.")

        logger.debug("Image upload validated")

        return ImageResult(
            file_name=file_name,
            file_size=len(raw_bytes_final),
            img_format=img_format,
            raw_bytes=raw_bytes_final,
            thumbnail_bytes=thumbnail_bytes,
            width=width,
            height=height,
            is_valid=True,
        )

    def get_supported_extensions(self) -> list[str]:
        """Return a list of supported file extensions."""
        return list(SUPPORTED_IMAGE_FORMATS.keys())

    def get_accepted_types_string(self) -> list[str]:
        """Return MIME types for Streamlit file_uploader `type` parameter."""
        return ["image/jpeg", "image/png", "image/gif", "image/webp"]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_magic_bytes(
        self, file_bytes: bytes, img_format: str, file_name: str
    ) -> Optional[str]:
        """
        Check file magic bytes to catch misnamed or corrupted files.
        Returns an error string if invalid, None if OK.
        """
        header = file_bytes[:12]

        MAGIC: dict[str, list[bytes]] = {
            "jpeg": [b"\xff\xd8\xff"],
            "png":  [b"\x89PNG\r\n\x1a\n"],
            "gif":  [b"GIF87a", b"GIF89a"],
            "webp": [b"RIFF"],  # RIFF....WEBP — needs full 12-byte header
        }

        expected = MAGIC.get(img_format, [])
        if expected:
            # WebP needs a special two-part check: RIFF at 0 and WEBP at 8
            if img_format == "webp":
                if len(file_bytes) < 12 or not (
                    file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"
                ):
                    return (
                        "File does not appear to be a valid WebP image. "
                        "It may be corrupted or misnamed."
                    )
            elif not any(header.startswith(m) for m in expected):
                return (
                    f"File does not appear to be a valid "
                    f"{img_format.upper()} image. It may be corrupted or misnamed."
                )

        return None

    def _process_with_pillow(
        self, file_bytes: bytes, img_format: str
    ) -> tuple[int, int, bytes, Optional[bytes], Optional[str]]:
        """Validate before decoding, bound all frames, and close image resources."""
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return 0, 0, file_bytes, None, "Image validation requires Pillow. Upload rejected."
        try:
            with ExitStack() as stack:
                def own(image):
                    stack.callback(image.close)
                    return image

                img = own(Image.open(io.BytesIO(file_bytes)))
                if (img.format or "").lower() != img_format:
                    raise ValueError("Image format does not match extension")
                width, height = img.size
                if (not 0 < width <= MAX_IMAGE_DIMENSION or not 0 < height <= MAX_IMAGE_DIMENSION
                        or width * height > MAX_IMAGE_PIXELS):
                    raise ValueError("Image dimensions exceed validation limits; resize the image")
                frames = getattr(img, "n_frames", 1)
                if frames > MAX_IMAGE_FRAMES or frames * width * height > MAX_TOTAL_FRAME_PIXELS:
                    raise ValueError("Animated image exceeds frame/pixel budget")
                img.verify()
                img = own(Image.open(io.BytesIO(file_bytes)))
                # Verify every frame sent to Bedrock, not just its thumbnail frame.
                frame_pixels = 0
                for frame in range(frames):
                    img.seek(frame)
                    w, h = img.size
                    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION or w * h > MAX_IMAGE_PIXELS:
                        raise ValueError("Frame dimensions exceed validation limits")
                    frame_pixels += w * h
                    if frame_pixels > MAX_TOTAL_FRAME_PIXELS:
                        raise ValueError("Total decoded frame budget exceeded")
                    img.load()
                img.seek(0)
                img = own(ImageOps.exif_transpose(img))
                width, height = img.size
                final_bytes = file_bytes
                if img_format == "jpeg" and img.mode not in ("RGB", "L", "CMYK"):
                    converted = own(img.convert("RGB"))
                    with io.BytesIO() as buf:
                        converted.save(buf, format="JPEG", quality=92)
                        final_bytes = buf.getvalue()
                thumb = own(img.copy())
                thumb.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
                if thumb.mode not in ("RGB", "RGBA", "L"):
                    thumb = own(thumb.convert("RGBA"))
                with io.BytesIO() as buf:
                    thumb.save(buf, format="PNG")
                    thumbnail = buf.getvalue()
                return width, height, final_bytes, thumbnail, None
        except Exception:
            return 0, 0, file_bytes, None, "Image is corrupt or exceeds dimension/frame limits. Please resize or re-export it."
