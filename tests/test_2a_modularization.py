"""Offline modularization regressions. Authored for user-run verification."""
import ast
import importlib
import runpy
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import test_1e_stream_integrity as fixtures
from tests.frontend_support import load_frontend

ROOT = Path(__file__).resolve().parents[1]


class TestModularization(fixtures.OfflineCase):
    def setUp(self):
        super().setUp()
        self.st = MagicMock()
        self.st.session_state = fixtures.SessionState()
        self.ui = load_frontend(self.st, self)

    def test_launcher_import_is_passive(self):
        with patch("novamind.ui.app.main") as main:
            namespace = runpy.run_path(str(ROOT / "mod_chatbot_frontend.py"), run_name="launcher_import")
            self.assertIs(namespace["main"], main)
            main.assert_not_called()
        self.st.set_page_config.assert_not_called()
        self.client.converse_stream.assert_not_called()

    def test_compatible_launcher_dispatches_each_rerun(self):
        with patch("novamind.ui.app.main") as main:
            for _ in range(2):
                runpy.run_path(str(ROOT / "mod_chatbot_frontend.py"), run_name="__main__")
            self.assertEqual(main.call_count, 2)

    def test_page_config_runs_before_render_on_every_main_call(self):
        with patch.object(self.ui, "_check_login", return_value=False), \
             patch.object(self.ui, "_render_login_page") as login, \
             patch.object(self.ui, "_inject_css") as style:
            def render_style():
                self.assertGreater(self.st.set_page_config.call_count, style.call_count - 1)
            style.side_effect = render_style
            self.ui.main()
            self.ui.main()
        self.assertEqual(self.st.set_page_config.call_count, 2)
        self.assertEqual(login.call_count, 2)
        self.client.converse_stream.assert_not_called()

    def test_domain_and_config_do_not_depend_on_streamlit_or_ui(self):
        for folder in ("domain", "config"):
            for path in (ROOT / "novamind" / folder).glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertFalse(any(name == "streamlit" or name.startswith("novamind.ui") for name in imports), str(path))

    def test_domain_state_is_explicit_and_isolated(self):
        session = importlib.import_module("novamind.domain.session")
        first, second = fixtures.SessionState(), fixtures.SessionState()
        from tests.offline_support import demo_state
        first.update(demo_state())
        second.update(demo_state())
        session._init_session_state(first)
        session._init_session_state(second)
        from services.authorization import publish_data
        publish_data(first, pending_image=object())
        first.chat_history.append({"role": "user", "text": "first"})
        session._init_session_state(first)
        self.assertIsNotNone(first.pending_image)
        self.assertIsNone(second.pending_image)
        self.assertEqual(second.chat_history, [])
        old_key = session._upload_widget_key(first)
        session._clear_conversation(first)
        self.assertNotEqual(session._upload_widget_key(first), old_key)
        self.assertEqual(first.chat_history, [])
        self.assertEqual(second.upload_generation, 0)

    def test_orchestrator_reuses_service_and_preserves_history_on_switch(self):
        self.ui._init_session_state()
        identity = self.st.session_state.auth_session
        first = Mock(model_id="amazon.nova-pro-v1:0", _auth_session=identity)
        second = Mock(model_id="amazon.nova-lite-v1:0", _auth_session=identity)
        history = self.st.session_state.bedrock_history
        history.append({"role": "user", "content": [{"text": "existing"}]})
        with patch.object(self.ui, "get_bedrock_service", side_effect=[first, second]) as factory:
            self.assertIs(self.ui._get_or_create_service(), first)
            self.assertIs(self.ui._get_or_create_service(), first)
            self.st.session_state.selected_model_label = "Amazon Nova Lite (Fast & Cheap)"
            self.assertIs(self.ui._get_or_create_service(), second)
        self.assertEqual(factory.call_count, 2)
        self.assertIs(self.st.session_state.bedrock_history, history)

    def test_asset_root_remains_project_root(self):
        settings = importlib.import_module("novamind.config.settings")
        self.assertEqual(settings.ROOT, ROOT)

    def test_authenticated_main_dispatches_chat_once(self):
        self.ui._init_session_state()
        self.st.session_state.login_user = "demo"
        self.st.chat_input.return_value = "question"
        with patch.object(self.ui, "_check_login", return_value=True), \
             patch.object(self.ui, "_render_sidebar"), \
             patch.object(self.ui, "_render_welcome"), \
             patch.object(self.ui, "_handle_user_input", return_value=True) as send:
            self.ui.main()
        send.assert_called_once_with("question")
        self.st.rerun.assert_called_once()
