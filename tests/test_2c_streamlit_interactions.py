"""Real Streamlit widgets/reruns; only the AWS client boundary is replaced."""
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import test_1e_stream_integrity as fixtures
from tests.offline_support import offline_environment

ROOT = Path(__file__).resolve().parents[1]


class TestStreamlitInteractions(fixtures.OfflineCase):
    def setUp(self):
        self.enterContext(offline_environment())
        super().setUp()
        self.enterContext(patch("services.bedrock_service.create_aws_client", return_value=self.client))
        self.app = self.new_app()

    def new_app(self):
        # Allow cold Streamlit initialization on slower hosts; retain a bounded
        # deadline without skipping authentication or retrying failed runs.
        app = AppTest.from_file(str(ROOT / "mod_chatbot_frontend.py"), default_timeout=60)
        from tests.offline_support import demo_state
        for key, value in demo_state().items():
            app.session_state[key] = value
        app.run()
        self.assertEqual(list(app.exception), [])
        return app

    def healthy(self):
        self.assertEqual(list(self.app.exception), [])

    def send(self, prompt="Explain this", events=None):
        stream = self.respond(events if events is not None else [fixtures.delta("Offline answer"), fixtures.stop()])
        self.app.chat_input[0].set_value(prompt).run()
        self.healthy()
        self.assertEqual(stream.closed, 1)
        return stream

    def upload(self, name="notes.txt", content=b"Document content", mime="text/plain"):
        self.app.file_uploader[0].set_value((name, content, mime)).run()
        self.healthy()

    def click(self, label):
        buttons = [button for button in self.app.button if button.label == label]
        self.assertEqual(len(buttons), 1, label)
        buttons[0].click().run()
        self.healthy()

    def last_content(self):
        messages = self.client.converse_stream.call_args.kwargs["messages"]
        return [message for message in messages if message["role"] == "user"][-1]["content"]

    def test_chat_and_followup_persist_once_across_reruns(self):
        self.send("First question")
        self.assertEqual(len(self.app.chat_message), 2)
        self.assertEqual(self.app.session_state["chat_history"][-1]["status"], "completed")
        self.assertEqual(len(self.app.session_state["bedrock_history"]), 2)
        self.app.run()
        self.healthy()
        self.client.converse_stream.assert_called_once()
        self.send("Follow up")
        self.assertEqual(len(self.app.session_state["bedrock_history"]), 4)
        self.assertEqual(len(self.app.chat_message), 4)
        self.assertIn("First question", str(self.client.converse_stream.call_args.kwargs["messages"]))

    def test_incomplete_output_is_displayed_but_excluded_from_context(self):
        self.send("Interrupted request", [fixtures.delta("Partial output")])
        self.assertEqual(self.app.session_state["bedrock_history"], [])
        assistant = self.app.session_state["chat_history"][-1]
        self.assertEqual((assistant["text"], assistant["status"]), ("Partial output", "incomplete"))
        self.assertGreater(len(self.app.warning), 0)
        self.assertTrue(any("Partial output" in item.value for item in self.app.markdown))
        self.send("Retry")
        self.assertNotIn("Interrupted request", str(self.client.converse_stream.call_args.kwargs["messages"]))

    def test_whitespace_prompt_keeps_attachment_without_invoking(self):
        self.upload()
        self.app.chat_input[0].set_value("   \t  ").run()
        self.healthy()
        self.client.converse_stream.assert_not_called()
        self.assertEqual(self.app.session_state["chat_history"], [])
        self.assertIsNotNone(self.app.session_state["pending_document"])
        self.assertTrue(any("Please enter a message" in item.value for item in self.app.warning))

    def test_upload_reruns_validate_once_send_consumes_selection(self):
        import novamind.orchestration.uploads as uploads
        with patch.object(uploads, "validate_file_upload", wraps=uploads.validate_file_upload) as validate:
            self.upload()
            for _ in range(2):
                self.app.run()
                self.healthy()
            validate.assert_called_once()
        key = self.app.file_uploader[0].key
        self.send()
        self.assertEqual(self.last_content()[0]["document"]["source"]["bytes"], b"Document content")
        self.assertIsNone(self.app.session_state["pending_document"])
        self.assertNotEqual(self.app.file_uploader[0].key, key)
        self.assertIsNone(self.app.file_uploader[0].value)
        self.send("Next question")
        self.assertEqual(self.last_content(), [{"text": "Next question"}])

    def test_invalid_replacement_cannot_reuse_valid_document(self):
        self.upload()
        self.upload("broken.png", b"invalid image", "image/png")
        self.assertIsNone(self.app.session_state["pending_document"])
        self.assertIsNone(self.app.session_state["pending_image"])
        self.assertGreater(len(self.app.error), 0)
        self.send("Text only")
        self.assertEqual(self.last_content(), [{"text": "Text only"}])

    def test_remove_button_clears_widget_and_next_request(self):
        self.upload()
        self.click("✕ Remove document")
        self.assertIsNone(self.app.file_uploader[0].value)
        self.assertIsNone(self.app.session_state["pending_document"])
        self.send("Text only")
        self.assertEqual(self.last_content(), [{"text": "Text only"}])

    def test_native_uploader_clear_updates_application_state(self):
        self.upload()
        self.app.file_uploader[0].clear().run()
        self.healthy()
        self.assertIsNone(self.app.session_state["pending_document"])
        self.assertIsNone(self.app.session_state["upload_error"])
        self.send("Text only")
        self.assertEqual(self.last_content(), [{"text": "Text only"}])

    def test_new_chat_clears_history_usage_and_pending_upload(self):
        self.send()
        self.upload()
        self.click("🔄 New")
        for key in ("chat_history", "bedrock_history", "usage_ledger"):
            self.assertEqual(self.app.session_state[key], [])
        self.assertIsNone(self.app.session_state["pending_document"])
        self.assertIsNone(self.app.file_uploader[0].value)
        self.assertEqual(self.app.session_state["conversation_count"], 1)
        self.send("Fresh question")
        messages = self.client.converse_stream.call_args.kwargs["messages"]
        self.assertEqual(messages, [{"role": "user", "content": [{"text": "Fresh question"}]}])

    def test_sessions_do_not_share_history_or_pending_uploads(self):
        self.send()
        self.upload()
        other = self.new_app()
        self.assertEqual(other.session_state["chat_history"], [])
        self.assertEqual(other.session_state["bedrock_history"], [])
        self.assertIsNone(other.session_state["pending_document"])
        self.assertEqual(len(self.app.session_state["chat_history"]), 2)
        self.assertIsNotNone(self.app.session_state["pending_document"])
