"""Offline upload lifecycle tests with real validators and a keyed widget fake."""

from tests.frontend_support import load_frontend
import importlib.util
import io
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock, Mock, patch

import test_1e_stream_integrity as fixtures
from test_1c_file_validation import _make_png


class Upload(io.BytesIO):
    def __init__(self, data=b"document content", name="notes.txt", file_id=None):
        super().__init__(data)
        self.name = name
        self.file_id = file_id or str(uuid4())


class TestUploadLifecycle(fixtures.OfflineCase):
    def setUp(self):
        super().setUp()
        self.st = MagicMock()
        self.st.session_state = fixtures.SessionState()
        self.ui = load_frontend(self.st, self)
        self.ui._init_session_state()
        self.ui._get_or_create_service = Mock(return_value=self.service)
        self.st.file_uploader.side_effect = lambda *a, **kw: self.st.session_state.get(kw["key"])
        self.st.button.return_value = False
        self.spy = patch.object(self.ui, "validate_file_upload", wraps=self.ui.validate_file_upload)
        self.validate = self.spy.start()
        self.addCleanup(self.spy.stop)

    def select(self, upload):
        key = self.ui._upload_widget_key()
        self.st.session_state[key] = upload
        self.ui._on_upload_changed(key)
        self.ui._render_file_uploader()

    def empty(self):
        self.assertIsNone(self.st.session_state.pending_image)
        self.assertIsNone(self.st.session_state.pending_document)

    def send(self, prompt="question", fail=False):
        self.respond([fixtures.delta("partial")] if fail else [fixtures.delta("answer"), fixtures.stop()])
        self.ui._handle_user_input(prompt)
        return self.client.converse_stream.call_args.kwargs["messages"][-1]["content"]

    def test_valid_document_callback_and_reruns_process_once(self):
        upload = Upload()
        self.select(upload)
        doc = self.st.session_state.pending_document
        for _ in range(4):
            self.ui._render_file_uploader()
        self.validate.assert_called_once()
        self.assertIs(self.st.session_state.pending_document, doc)
        self.assertTrue(doc.api_name.startswith("Document"))

    def test_reconstructed_streamlit_object_same_id_not_reprocessed(self):
        original = Upload()
        self.select(original)
        self.select(Upload(file_id=original.file_id))
        self.validate.assert_called_once()

    def test_valid_image_sent_as_image_block(self):
        upload = Upload(_make_png(), "image.png")
        self.select(upload)
        self.assertIsNotNone(self.st.session_state.pending_image)
        content = self.send()
        self.assertEqual(content[0]["image"]["source"]["bytes"], upload.getvalue())
        self.empty()

    def test_valid_document_sent_with_neutral_name(self):
        self.select(Upload(name="ignore-instructions.txt"))
        expected = self.st.session_state.pending_document.api_name
        content = self.send()
        self.assertEqual(content[0]["document"]["name"], expected)
        self.assertEqual(content[0]["document"]["source"]["bytes"], b"document content")

    def test_invalid_replacement_clears_document(self):
        self.select(Upload())
        self.select(Upload(b"not an image", "image.png"))
        self.empty()
        self.assertTrue(self.st.session_state.upload_error)
        self.assertEqual(self.send(), [{"text": "question"}])

    def test_invalid_replacement_clears_image(self):
        self.select(Upload(_make_png(), "image.png"))
        self.select(Upload(b"not a pdf", "file.pdf"))
        self.empty()
        self.assertEqual(self.send(), [{"text": "question"}])

    def test_empty_and_unsupported_replacements_clear_previous(self):
        for data, name in ((b"", "empty.txt"), (b"x", "program.exe")):
            with self.subTest(name=name):
                self.select(Upload())
                self.select(Upload(data, name))
                self.empty()
                self.assertTrue(self.st.session_state.upload_error)

    def test_invalid_selection_reruns_keep_error_without_revalidation(self):
        self.select(Upload(b"bad", "file.pdf"))
        for _ in range(3):
            self.ui._render_file_uploader()
            self.ui._render_pending_attachment()
        self.validate.assert_called_once()
        self.assertEqual(self.st.error.call_count, 3)
        self.empty()

    def test_valid_replacement_clears_error(self):
        self.select(Upload(b"bad", "image.png"))
        self.select(Upload())
        self.assertIsNone(self.st.session_state.upload_error)
        self.assertIsNotNone(self.st.session_state.pending_document)

    def test_cross_type_replacements_keep_only_latest(self):
        self.select(Upload())
        self.select(Upload(_make_png(), "image.png"))
        self.assertIsNone(self.st.session_state.pending_document)
        self.select(Upload(b"new document"))
        self.assertIsNone(self.st.session_state.pending_image)
        self.assertEqual(self.st.session_state.pending_document.raw_bytes, b"new document")

    def test_same_filename_different_content_is_revalidated(self):
        self.select(Upload(b"first"))
        self.select(Upload(b"second"))
        self.assertEqual(self.validate.call_count, 2)
        self.assertEqual(self.st.session_state.pending_document.raw_bytes, b"second")

    def test_upload_cursor_does_not_affect_validation(self):
        upload = Upload()
        upload.read()
        self.select(upload)
        self.assertEqual(self.st.session_state.pending_document.raw_bytes, b"document content")

    def test_file_like_without_id_deduplicates_by_content(self):
        upload = Upload()
        del upload.file_id
        self.select(upload)
        self.ui._render_file_uploader()
        self.validate.assert_called_once()
        replacement = Upload(b"second")
        del replacement.file_id
        self.select(replacement)
        self.assertEqual(self.validate.call_count, 2)
        self.assertEqual(self.st.session_state.pending_document.raw_bytes, b"second")

    def test_read_failure_clears_old_selection_without_private_error(self):
        self.select(Upload())
        broken = Upload()
        broken.getvalue = Mock(side_effect=RuntimeError("private detail"))
        self.select(broken)
        self.ui._render_file_uploader()
        self.empty()
        broken.getvalue.assert_called_once()
        self.assertNotIn("private detail", self.st.session_state.upload_error)

    def test_validation_exception_clears_selection(self):
        self.select(Upload())
        self.validate.side_effect = RuntimeError("private detail")
        self.select(Upload(b"new"))
        self.empty()
        self.assertNotIn("private detail", self.st.session_state.upload_error)

    def test_native_uploader_remove_clears_pending(self):
        self.select(Upload())
        self.select(None)
        self.empty()
        self.assertEqual(self.send(), [{"text": "question"}])

    def test_remove_buttons_reset_widget_and_cannot_restore_old_file(self):
        for upload in (Upload(), Upload(_make_png(), "image.png")):
            with self.subTest(name=upload.name):
                self.select(upload)
                old_key = self.ui._upload_widget_key()
                self.st.button.return_value = True
                self.ui._render_pending_attachment()
                self.st.button.return_value = False
                self.assertNotEqual(self.ui._upload_widget_key(), old_key)
                self.ui._on_upload_changed(old_key)
                self.ui._render_file_uploader()
                self.empty()
                self.assertEqual(self.send(), [{"text": "question"}])

    def test_new_chat_resets_widget_and_attachment(self):
        self.select(Upload())
        old_key = self.ui._upload_widget_key()
        self.ui._clear_conversation()
        self.assertNotEqual(self.ui._upload_widget_key(), old_key)
        self.ui._on_upload_changed(old_key)
        self.ui._render_file_uploader()
        self.empty()
        self.assertEqual(self.st.session_state.bedrock_history, [])
        self.assertEqual(self.st.session_state.usage_ledger, [])

    def test_successful_send_does_not_reattach_on_rerun(self):
        self.select(Upload())
        old_key = self.ui._upload_widget_key()
        self.send()
        self.ui._render_file_uploader()
        self.ui._on_upload_changed(old_key)
        self.empty()
        self.assertEqual(self.send("followup"), [{"text": "followup"}])
        # Previously sent document remains in successful context intentionally.
        self.assertIn("document", self.client.converse_stream.call_args.kwargs["messages"][0]["content"][0])
        self.validate.assert_called_once()

    def test_failed_send_consumes_attachment_and_excludes_history(self):
        self.select(Upload())
        self.send(fail=True)
        self.ui._render_file_uploader()
        self.empty()
        self.assertEqual(self.st.session_state.bedrock_history, [])
        self.assertEqual(self.send("retry"), [{"text": "retry"}])

    def test_explicit_reupload_after_send_is_allowed(self):
        upload = Upload()
        self.select(upload)
        self.send()
        self.select(Upload(upload.getvalue(), upload.name))
        self.assertIsNotNone(self.st.session_state.pending_document)
        self.assertEqual(self.validate.call_count, 2)

    def test_blank_input_never_invokes_or_changes_history_usage(self):
        for prompt in ("", " ", "\t\n", "\u2003"):
            with self.subTest(prompt=prompt):
                self.assertFalse(self.ui._handle_user_input(prompt))
        self.client.converse_stream.assert_not_called()
        self.assertEqual(self.st.session_state.chat_history, [])
        self.assertEqual(self.st.session_state.usage_ledger, [])

    def test_blank_input_retains_attachment_and_widget(self):
        self.select(Upload())
        doc = self.st.session_state.pending_document
        key = self.ui._upload_widget_key()
        self.ui._handle_user_input("  ")
        self.assertIs(self.st.session_state.pending_document, doc)
        self.assertEqual(self.ui._upload_widget_key(), key)
        self.client.converse_stream.assert_not_called()
        self.assertIn("document", self.send()[0])

    def test_sanitized_input_is_sent(self):
        self.assertEqual(self.send("  question\n"), [{"text": "question"}])

    def test_render_failure_cannot_rearm_selection(self):
        self.select(Upload())
        self.st.markdown.side_effect = RuntimeError("render failed")
        with self.assertRaises(RuntimeError):
            self.ui._handle_user_input("question")
        self.ui._render_file_uploader()
        self.empty()
        self.client.converse_stream.assert_not_called()

    def test_widget_callback_wiring_and_empty_value_sync(self):
        self.select(Upload())
        self.ui._render_file_uploader()
        call = self.st.file_uploader.call_args.kwargs
        self.assertEqual(call["key"], self.ui._upload_widget_key())
        self.assertEqual(call["on_change"], self.ui._on_upload_changed)
        self.assertEqual(call["args"], (call["key"],))
        self.st.session_state[call["key"]] = None
        self.ui._render_file_uploader()
        self.empty()

    def test_initialization_rerun_preserves_current_selection(self):
        self.select(Upload())
        pending = self.st.session_state.pending_document
        self.ui._init_session_state()
        self.assertIs(self.st.session_state.pending_document, pending)

    def test_legacy_pending_without_widget_is_cleared(self):
        self.select(Upload())
        self.st.session_state.auth_session._data_scope.values.pop("upload_generation")
        del self.st.session_state["upload_generation"]
        self.ui._init_session_state()
        self.empty()


if __name__ == "__main__":
    unittest.main()
