"""
tests/test_1c_file_validation.py
──────────────────────────────────
Task 1C regression tests — multimodal file validation.

Covers:
  A. ImageService — size limits (3.75 MB Bedrock limit)
  B. ImageService — dimension limits (8,000 px per side)
  C. ImageService — corrupt/truncated file rejection via Pillow full decode
  D. ImageService — valid files still pass end-to-end
  E. ImageService — Pillow-absent validation fails closed
  F. DocumentService — size/integrity checks unchanged
  G. Validators — dispatcher still routes correctly
  H. MAX constants exported correctly

All tests are fully offline.  No AWS calls, no network, no Streamlit.
"""

import io
import struct
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Image factories ───────────────────────────────────────────────────────────

def _make_png(width: int = 10, height: int = 10) -> bytes:
    """Generate a minimal valid PNG of any dimension in pure Python."""
    def _chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # Build raw image rows: one filter byte + RGB per pixel, all zeros (black)
    row = b"\x00" + b"\x00\x00\x00" * width
    raw_rows = row * height
    idat = zlib.compress(raw_rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def _make_jpeg(width: int = 10, height: int = 10) -> bytes:
    """Generate a valid JPEG; Pillow is a required dependency."""
    from PIL import Image
    with Image.new("RGB", (width, height), color=(255, 0, 0)) as img:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def _make_minimal_pdf() -> bytes:
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# A. Size limit — 3.75 MB
# ═════════════════════════════════════════════════════════════════════════════

class TestImageSizeLimit(unittest.TestCase):

    def setUp(self):
        from services.image_service import ImageService, MAX_IMAGE_SIZE_BYTES, ImageValidationError
        self.service = ImageService()
        self.limit = MAX_IMAGE_SIZE_BYTES
        self.ImageValidationError = ImageValidationError

    def test_limit_is_3_75_mb(self):
        expected = 3 * 1024 * 1024 + 768 * 1024   # 3,932,160 bytes
        self.assertEqual(self.limit, expected)

    def test_file_exactly_at_limit_triggers_error(self):
        oversized = b"\xff\xd8\xff" + b"\x00" * (self.limit - 2)
        result = self.service.process(oversized, "big.jpg")
        self.assertIsInstance(result, self.ImageValidationError)
        self.assertIn("too large", result.error_message.lower())

    def test_file_one_byte_over_limit_rejected(self):
        oversized = b"\xff\xd8\xff" + b"\x00" * self.limit
        result = self.service.process(oversized, "over.jpg")
        self.assertIsInstance(result, self.ImageValidationError)

    def test_file_well_within_limit_passes_size_check(self):
        """A 1 KB file must not be rejected on size."""
        tiny = _make_png(5, 5)
        result = self.service.process(tiny, "tiny.png")
        from services.image_service import ImageResult
        self.assertIsInstance(result, ImageResult)
        self.assertTrue(result.is_valid)

    def test_error_message_mentions_bedrock(self):
        oversized = b"\xff\xd8\xff" + b"\x00" * self.limit
        result = self.service.process(oversized, "over.jpg")
        self.assertIn("Bedrock", result.error_message)


# ═════════════════════════════════════════════════════════════════════════════
# B. Dimension limit — 8,000 px
# ═════════════════════════════════════════════════════════════════════════════

class TestImageDimensionLimit(unittest.TestCase):

    def setUp(self):
        from services.image_service import ImageService, MAX_IMAGE_DIMENSION, ImageValidationError
        self.service = ImageService()
        self.max_dim = MAX_IMAGE_DIMENSION
        self.ImageValidationError = ImageValidationError

    def test_max_dimension_constant_is_8000(self):
        self.assertEqual(self.max_dim, 8_000)

    def test_image_within_limits_passes(self):
        valid_png = _make_png(100, 100)
        result = self.service.process(valid_png, "ok.png")
        from services.image_service import ImageResult
        self.assertIsInstance(result, ImageResult)
        self.assertEqual((result.width, result.height), (100, 100))

    def test_image_exceeding_width_rejected(self):
        """Mock Pillow to report a width > 8000 without needing a real giant image."""
        valid_png = _make_png(10, 10)
        with patch("services.image_service.ImageService._process_with_pillow") as mock_proc:
            mock_proc.return_value = (8001, 100, valid_png, None, None)
            result = self.service.process(valid_png, "wide.png")
        self.assertIsInstance(result, self.ImageValidationError)
        self.assertIn("8001", result.error_message)
        self.assertIn("8000", result.error_message)

    def test_image_exceeding_height_rejected(self):
        valid_png = _make_png(10, 10)
        with patch("services.image_service.ImageService._process_with_pillow") as mock_proc:
            mock_proc.return_value = (100, 9000, valid_png, None, None)
            result = self.service.process(valid_png, "tall.png")
        self.assertIsInstance(result, self.ImageValidationError)
        self.assertIn("9000", result.error_message)

    def test_image_at_exactly_8000_passes(self):
        """8,000 × 1 is within the limit (limit is 8,000, not 7,999)."""
        valid_png = _make_png(10, 10)
        with patch("services.image_service.ImageService._process_with_pillow") as mock_proc:
            mock_proc.return_value = (8000, 1, valid_png, None, None)
            result = self.service.process(valid_png, "edge.png")
        from services.image_service import ImageResult
        self.assertIsInstance(result, ImageResult)
        self.assertEqual((result.width, result.height), (8000, 1))

    def test_dimension_error_mentions_resize(self):
        valid_png = _make_png(10, 10)
        with patch("services.image_service.ImageService._process_with_pillow") as mock_proc:
            mock_proc.return_value = (10000, 200, valid_png, None, None)
            result = self.service.process(valid_png, "huge.png")
        self.assertIn("resize", result.error_message.lower())


# ═════════════════════════════════════════════════════════════════════════════
# C. Corrupt / truncated file rejection
# ═════════════════════════════════════════════════════════════════════════════

class TestCorruptImageRejection(unittest.TestCase):

    def setUp(self):
        from services.image_service import ImageService, ImageValidationError, ImageResult
        self.service = ImageService()
        self.ImageValidationError = ImageValidationError
        self.ImageResult = ImageResult

    def test_pillow_decode_error_returned_as_validation_error(self):
        """_process_with_pillow returning an error string must become ImageValidationError."""
        valid_png = _make_png(5, 5)
        with patch("services.image_service.ImageService._process_with_pillow") as mock_proc:
            mock_proc.return_value = (0, 0, valid_png, None, "Corrupt: truncated data")
            result = self.service.process(valid_png, "corrupt.png")
        self.assertIsInstance(result, self.ImageValidationError)
        self.assertIn("corrupt", result.error_message.lower())
        self.assertFalse(result.is_valid)

    def test_truncated_jpeg_body_rejected(self):
        """A JPEG with valid magic bytes but truncated body must be rejected."""
        # Valid JPEG SOI marker + garbage — passes magic-bytes, fails Pillow decode
        truncated = b"\xff\xd8\xff\xe0" + b"\x00\x0a\x4a\x46\x49\x46\x00\x01" + b"\xde\xad\xbe\xef" * 5
        result = self.service.process(truncated, "truncated.jpg")
        self.assertIsInstance(result, self.ImageValidationError)
        self.assertFalse(result.is_valid)
        self.assertNotIn("too large", result.error_message.lower())

    def test_valid_png_passes_corruption_check(self):
        """A properly formed PNG must pass the Pillow decode stage."""
        valid_png = _make_png(20, 20)
        result = self.service.process(valid_png, "valid.png")
        self.assertIsInstance(result, self.ImageResult)
        self.assertTrue(result.is_valid)

    def test_empty_bytes_rejected_early(self):
        result = self.service.process(b"", "empty.png")
        self.assertIsInstance(result, self.ImageValidationError)
        self.assertIn("empty", result.error_message.lower())


# ═════════════════════════════════════════════════════════════════════════════
# D. Valid files pass end-to-end
# ═════════════════════════════════════════════════════════════════════════════

class TestValidImagesPassEndToEnd(unittest.TestCase):

    def setUp(self):
        from services.image_service import ImageService, ImageResult
        self.service = ImageService()
        self.ImageResult = ImageResult

    def test_valid_png_produces_image_result(self):
        png = _make_png(100, 100)
        result = self.service.process(png, "photo.png")
        self.assertIsInstance(result, self.ImageResult)
        self.assertTrue(result.is_valid)

    def test_valid_png_has_correct_dimensions(self):
        png = _make_png(50, 80)
        result = self.service.process(png, "photo.png")
        self.assertIsInstance(result, self.ImageResult)
        self.assertEqual(result.width, 50)
        self.assertEqual(result.height, 80)

    def test_valid_jpeg_produces_image_result(self):
        jpeg = _make_jpeg(30, 30)
        result = self.service.process(jpeg, "photo.jpg")
        self.assertIsInstance(result, self.ImageResult)
        self.assertTrue(result.is_valid)

    def test_file_size_in_result_is_positive(self):
        png = _make_png(10, 10)
        result = self.service.process(png, "test.png")
        self.assertIsInstance(result, self.ImageResult)
        self.assertGreater(result.file_size, 0)

    def test_raw_bytes_non_empty(self):
        png = _make_png(10, 10)
        result = self.service.process(png, "test.png")
        self.assertIsInstance(result, self.ImageResult)
        self.assertTrue(result.raw_bytes)

    def test_result_is_valid_flag(self):
        png = _make_png(10, 10)
        result = self.service.process(png, "test.png")
        self.assertIsInstance(result, self.ImageResult)
        self.assertTrue(result.is_valid)


# ═════════════════════════════════════════════════════════════════════════════
# E. Pillow-absent fail-closed path
# ═════════════════════════════════════════════════════════════════════════════

class TestPillowAbsent(unittest.TestCase):
    def test_pillow_missing_validation_fails_closed(self):
        from services.image_service import ImageService
        with patch.dict("sys.modules", {"PIL": None}):
            result = ImageService().process(_make_png(), "file.png")
        self.assertFalse(result.is_valid)
        self.assertIn("Pillow", result.error_message)

    def test_zero_dimensions_fail_closed(self):
        from services.image_service import ImageService
        with patch("services.image_service.ImageService._process_with_pillow",
                   return_value=(0, 0, _make_png(), None, None)):
            result = ImageService().process(_make_png(), "file.png")
        self.assertFalse(result.is_valid)


# ═════════════════════════════════════════════════════════════════════════════
# F. DocumentService — existing checks preserved
# ═════════════════════════════════════════════════════════════════════════════

class TestDocumentServicePreserved(unittest.TestCase):

    def setUp(self):
        from services.document_service import DocumentService, DocumentValidationError, DocumentResult
        import services.document_service as dm
        dm._doc_api_counter = 0
        self.service = DocumentService()
        self.DocumentValidationError = DocumentValidationError
        self.DocumentResult = DocumentResult

    def test_pdf_over_limit_rejected(self):
        from services.document_service import MAX_DOC_SIZE_BYTES
        oversized = b"%PDF-1.4 " + b"x" * (MAX_DOC_SIZE_BYTES + 1)
        result = self.service.process(oversized, "huge.pdf")
        self.assertIsInstance(result, self.DocumentValidationError)
        self.assertIn("too large", result.error_message.lower())

    def test_valid_pdf_passes(self):
        result = self.service.process(_make_minimal_pdf(), "doc.pdf")
        self.assertIsInstance(result, self.DocumentResult)
        self.assertTrue(result.is_valid)

    def test_pdf_wrong_header_rejected(self):
        bad_pdf = b"NOT_A_PDF" + b"\x00" * 100
        result = self.service.process(bad_pdf, "bad.pdf")
        self.assertIsInstance(result, self.DocumentValidationError)
        self.assertIn("valid PDF", result.error_message)

    def test_txt_file_accepted(self):
        txt = b"Hello, this is a plain text document.\n" * 10
        result = self.service.process(txt, "notes.txt")
        self.assertIsInstance(result, self.DocumentResult)
        self.assertTrue(result.is_valid)

    def test_empty_file_rejected(self):
        result = self.service.process(b"", "empty.pdf")
        self.assertIsInstance(result, self.DocumentValidationError)


# ═════════════════════════════════════════════════════════════════════════════
# G. Validators dispatcher
# ═════════════════════════════════════════════════════════════════════════════

class TestValidatorsDispatcher(unittest.TestCase):

    def setUp(self):
        from utils.validators import validate_file_upload
        from services.image_service import ImageResult, ImageValidationError
        from services.document_service import DocumentResult, DocumentValidationError
        self.validate = validate_file_upload
        self.ImageResult = ImageResult
        self.ImageValidationError = ImageValidationError
        self.DocumentResult = DocumentResult
        self.DocumentValidationError = DocumentValidationError

    def test_png_routed_to_image_service(self):
        png = _make_png(10, 10)
        result = self.validate(png, "photo.png")
        self.assertIsInstance(result, self.ImageResult)

    def test_pdf_routed_to_document_service(self):
        result = self.validate(_make_minimal_pdf(), "doc.pdf")
        self.assertIsInstance(result, self.DocumentResult)

    def test_unknown_extension_returns_error(self):
        result = self.validate(b"data", "file.xyz")
        self.assertFalse(result.is_valid)
        self.assertIn("Unsupported", result.error_message)

    def test_oversized_image_rejected_via_dispatcher(self):
        from services.image_service import MAX_IMAGE_SIZE_BYTES
        oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * MAX_IMAGE_SIZE_BYTES
        result = self.validate(oversized, "big.png")
        self.assertFalse(result.is_valid)


# ═════════════════════════════════════════════════════════════════════════════
# H. Constants exported correctly
# ═════════════════════════════════════════════════════════════════════════════

class TestConstantsExported(unittest.TestCase):

    def test_max_image_size_bytes_accessible(self):
        from services.image_service import MAX_IMAGE_SIZE_BYTES
        self.assertEqual(MAX_IMAGE_SIZE_BYTES, 3 * 1024 * 1024 + 768 * 1024)

    def test_max_image_dimension_accessible(self):
        from services.image_service import MAX_IMAGE_DIMENSION
        self.assertEqual(MAX_IMAGE_DIMENSION, 8_000)

    def test_max_doc_size_bytes_unchanged(self):
        from services.document_service import MAX_DOC_SIZE_BYTES
        self.assertEqual(MAX_DOC_SIZE_BYTES, 4 * 1024 * 1024 + 512 * 1024)

    def test_supported_image_formats_unchanged(self):
        from services.image_service import SUPPORTED_IMAGE_FORMATS
        self.assertIn(".jpg", SUPPORTED_IMAGE_FORMATS)
        self.assertIn(".png", SUPPORTED_IMAGE_FORMATS)
        self.assertIn(".gif", SUPPORTED_IMAGE_FORMATS)
        self.assertIn(".webp", SUPPORTED_IMAGE_FORMATS)

    def test_supported_doc_formats_unchanged(self):
        from services.document_service import SUPPORTED_DOC_FORMATS
        self.assertIn(".pdf", SUPPORTED_DOC_FORMATS)
        self.assertIn(".docx", SUPPORTED_DOC_FORMATS)
        self.assertIn(".csv", SUPPORTED_DOC_FORMATS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
