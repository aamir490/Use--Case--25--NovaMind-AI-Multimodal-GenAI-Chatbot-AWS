"""Offline regressions for sensitive upload metadata in application logs."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.document_service import DocumentService
from services.image_service import ImageService
from services import document_service, image_service
from novamind.orchestration import uploads
from tests.test_1c_file_validation import _make_png


class TestUploadLogPrivacy(unittest.TestCase):
    def test_image_processing_does_not_log_original_filename(self):
        filename = "private-customer-image.png"
        with patch.object(image_service.logger, "debug") as emit:
            result = ImageService().process(_make_png(), filename)

        self.assertTrue(result.is_valid)
        self.assertNotIn(filename, repr(emit.call_args_list))

    def test_document_processing_does_not_log_name_or_document_text(self):
        filename = "confidential-acquisition-notes.txt"
        contents = b"Private acquisition plan: Project Northstar"
        with patch.object(document_service.logger, "debug") as emit:
            result = DocumentService().process(contents, filename)

        self.assertTrue(result.is_valid)
        emitted = repr(emit.call_args_list)
        self.assertNotIn(filename, emitted)
        self.assertNotIn(contents.decode(), emitted)

    def test_oversized_streamlit_upload_is_rejected_before_copy(self):
        scope = object()
        state = SimpleNamespace(upload_identity=None, pending_image=None,
                                pending_document=None, upload_error=None,
                                attachment_id=None)
        upload = SimpleNamespace(name="notes.txt", file_id="upload-1",
                                 size=document_service.MAX_DOC_SIZE_BYTES + 1,
                                 getvalue=Mock())
        with (patch.object(uploads, "capture_scope", return_value=scope),
              patch.object(uploads, "publish_data") as publish,
              patch.object(uploads, "validate_file_upload") as validate):
            uploads._handle_file_upload(state, upload)

        upload.getvalue.assert_not_called()
        validate.assert_not_called()
        self.assertEqual(publish.call_args.kwargs["upload_error"],
                         "File exceeds the allowed size. Upload a smaller file.")


if __name__ == "__main__":
    unittest.main()
