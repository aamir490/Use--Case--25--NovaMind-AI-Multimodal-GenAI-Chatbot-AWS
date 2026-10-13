"""Focused offline parser/resource regressions; generated fixtures only."""
import io
import subprocess
import unittest
import zipfile
from unittest.mock import Mock, patch

from services.image_service import ImageService, MAX_IMAGE_SIZE_BYTES
from services.document_service import DocumentService
from services import document_parser as parser
from utils.validators import validate_file_upload
from tests.test_1c_file_validation import _make_png, _make_minimal_pdf


def package(fmt="docx", extra=None):
    main = "word/document.xml" if fmt == "docx" else "xl/workbook.xml"
    kind = "wordprocessingml.document" if fmt == "docx" else "spreadsheetml.sheet"
    root = ('<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><body/></document>'
            if fmt == "docx" else '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets/></workbook>')
    files = {
        main: root,
        "[Content_Types].xml": f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/{main}" ContentType="application/vnd.openxmlformats-officedocument.{kind}.main+xml"/></Types>',
        "_rels/.rels": f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{main}"/></Relationships>',
    }
    files.update(extra or {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


class TestImageResourceLimits(unittest.TestCase):
    def test_pillow_absence_rejected_by_dispatcher(self):
        with patch.dict("sys.modules", {"PIL": None}):
            self.assertFalse(validate_file_upload(_make_png(), "file.png").is_valid)

    def test_dimensions_checked_before_decode_and_resource_closed(self):
        fake = Mock(size=(8001, 1), format="PNG")
        with patch("PIL.Image.open", return_value=fake):
            result = ImageService().process(_make_png(), "file.png")
        self.assertFalse(result.is_valid)
        fake.load.assert_not_called()
        fake.close.assert_called_once()

    def test_total_pixel_budget_before_decode(self):
        fake = Mock(size=(5000, 5000), format="PNG")
        with patch("PIL.Image.open", return_value=fake):
            self.assertFalse(ImageService().process(_make_png(), "file.png").is_valid)
        fake.load.assert_not_called()

    def test_frame_limit_before_decode(self):
        fake = Mock(size=(10, 10), format="GIF", n_frames=33)
        with patch("PIL.Image.open", return_value=fake):
            self.assertFalse(ImageService().process(b"GIF89a", "file.gif").is_valid)
        fake.load.assert_not_called()

    def test_postprocessing_size_limit(self):
        with patch.object(ImageService, "_process_with_pillow", return_value=(1, 1, b"x" * 101, None, None)):
            self.assertFalse(ImageService(max_size_bytes=100).process(_make_png(), "file.png").is_valid)

    def test_postprocessing_exact_limit(self):
        with patch.object(ImageService, "_process_with_pillow", return_value=(1, 1, b"x" * 100, None, None)):
            self.assertTrue(ImageService(max_size_bytes=100).process(_make_png(), "file.png").is_valid)

    def test_custom_limit_cannot_bypass_bedrock_limit(self):
        with patch.object(ImageService, "_process_with_pillow") as decode:
            result = ImageService(max_size_bytes=MAX_IMAGE_SIZE_BYTES * 2).process(b"x" * (MAX_IMAGE_SIZE_BYTES + 1), "file.png")
        self.assertFalse(result.is_valid)
        decode.assert_not_called()

    def test_valid_all_image_formats(self):
        from PIL import Image
        with Image.new("RGB", (3, 3)) as img:
            for fmt in ("PNG", "JPEG", "GIF", "WEBP"):
                buf = io.BytesIO()
                img.save(buf, format=fmt)
                self.assertTrue(ImageService().process(buf.getvalue(), "file." + fmt.lower()).is_valid, fmt)


class TestDocumentParserLimits(unittest.TestCase):
    def test_real_pdf_worker_accepts_valid_file(self):
        result = DocumentService().process(_make_minimal_pdf(), "file.pdf")
        self.assertTrue(result.is_valid, result.error_message)
        self.assertEqual(result.page_count, 1)

    def test_fake_pdf_markers_rejected(self):
        self.assertFalse(DocumentService().process(b"%PDF-1.4\nfake\nstartxref\n0\n%%EOF", "file.pdf").is_valid)

    def test_truncated_pdf_rejected(self):
        self.assertFalse(DocumentService().process(_make_minimal_pdf()[:-20], "file.pdf").is_valid)

    def test_encrypted_pdf_rejected(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(100, 100)
        writer.encrypt("password")
        buf = io.BytesIO()
        writer.write(buf)
        self.assertFalse(DocumentService().process(buf.getvalue(), "file.pdf").is_valid)

    def test_pdf_page_limit(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(201):
            writer.add_blank_page(100, 100)
        buf = io.BytesIO()
        writer.write(buf)
        self.assertFalse(DocumentService().process(buf.getvalue(), "file.pdf").is_valid)

    def test_missing_pdf_dependency_fails(self):
        data = _make_minimal_pdf()
        with patch.dict("sys.modules", {"pypdf": None}):
            with self.assertRaises(ImportError):
                parser.validate_pdf(data)

    def test_missing_legacy_dependency_fails(self):
        with patch.dict("sys.modules", {"olefile": None}):
            with self.assertRaises(ImportError):
                parser.validate_legacy(b"fake", "doc")

    def test_worker_timeout_and_crash_fail_safely(self):
        for error in (subprocess.TimeoutExpired("worker", 8), subprocess.CalledProcessError(1, "worker")):
            with patch("services.document_service.subprocess.run", side_effect=error):
                result = DocumentService().process(_make_minimal_pdf(), "file.pdf")
            self.assertFalse(result.is_valid)
            self.assertIn("validation", result.error_message)

    def test_valid_docx_and_xlsx_worker(self):
        for fmt in ("docx", "xlsx"):
            result = DocumentService().process(package(fmt), "file." + fmt)
            self.assertTrue(result.is_valid, result.error_message)

    def test_corrupt_office_headers_rejected(self):
        for fmt in ("docx", "xlsx", "doc", "xls"):
            self.assertFalse(DocumentService().process(b"PK\x03\x04junk", "file." + fmt).is_valid)

    def test_wrong_office_format_rejected(self):
        self.assertFalse(DocumentService().process(package(), "file.xlsx").is_valid)

    def test_zip_bomb_rejected(self):
        with self.assertRaises(ValueError):
            parser.validate_ooxml(package(extra={"bomb.bin": b"0" * 100000}), "docx")

    def test_missing_main_relationship_rejected(self):
        with self.assertRaises(ValueError):
            parser.validate_ooxml(package(extra={"_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'}), "docx")

    def test_archive_path_and_xml_corruption_rejected(self):
        for extra in ({"../escape": "x"}, {"broken.xml": "<broken>"}, {"_rels/.rels": "garbage"}):
            with self.assertRaises(Exception):
                parser.validate_ooxml(package(extra=extra), "docx")

    def test_entity_and_deep_xml_rejected(self):
        for data in (b'<!DOCTYPE x [<!ENTITY e "a">]><x>&e;</x>',
                     ('<!DOCTYPE x [<!ENTITY e "a">]><x>&e;</x>').encode("utf-16"),
                     b"<x>" * 65 + b"</x>" * 65):
            with self.assertRaises(ValueError):
                parser.xml_root(data)

    def test_member_and_expansion_budgets(self):
        for setting, value in (("MAX_MEMBERS", 2), ("MAX_PART_BYTES", 10), ("MAX_EXPANDED_BYTES", 50)):
            with patch.object(parser, setting, value), self.assertRaises(ValueError):
                parser.validate_ooxml(package(), "docx")

    def test_missing_referenced_office_part(self):
        extra = {"word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="image" Target="media/missing.png"/></Relationships>'}
        with self.assertRaises(ValueError):
            parser.validate_ooxml(package(extra=extra), "docx")

    def test_duplicate_archive_members_rejected(self):
        buf = io.BytesIO(package())
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(buf, "a") as archive:
                archive.writestr("word/document.xml", "duplicate")
        with self.assertRaises(ValueError):
            parser.validate_ooxml(buf.getvalue(), "docx")

    def test_pdf_expansion_budget_in_worker(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        writer = PdfWriter()
        page = writer.add_blank_page(100, 100)
        stream = DecodedStreamObject()
        stream.set_data(b" " * (parser.MAX_PART_BYTES + 1))
        page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
        buf = io.BytesIO()
        writer.write(buf)
        self.assertFalse(DocumentService().process(buf.getvalue(), "file.pdf").is_valid)

    def test_plain_text_still_works_without_document_parsers(self):
        with patch("services.document_service.subprocess.run") as worker:
            self.assertTrue(validate_file_upload(b"hello", "file.txt").is_valid)
        worker.assert_not_called()
