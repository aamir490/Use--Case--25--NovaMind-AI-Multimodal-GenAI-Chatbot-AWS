"""Presentation smoke checks with mocked Streamlit and blocked network."""
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.frontend_support import load_frontend
from tests.offline_support import offline_environment, offline_guard


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class TestPremiumUI(unittest.TestCase):
    def setUp(self):
        self.enterContext(offline_environment())
        self.enterContext(offline_guard())
        self.st = MagicMock()
        self.st.session_state = State()
        self.st.columns.side_effect = lambda spec, **kw: [
            MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
        self.st.button.return_value = False
        self.st.selectbox.side_effect = lambda label, options, **kw: list(options)[kw.get("index", 0)]
        self.ui = load_frontend(self.st, self)
        self.ui._init_session_state()

    def test_local_png_branding_uses_one_image_and_deployment_root(self):
        from novamind.config.settings import ROOT
        self.assertEqual(self.ui._load_logo_bytes(), (ROOT / "novamind-logo.png").read_bytes())
        markup = self.ui._brand_html()
        self.assertEqual(markup.count("<img "), 1)
        self.assertIn("NovaMind AI", markup)
        self.assertIn("Built By Aamir", markup)
        encoded = markup.split("data:image/png;base64,", 1)[1].split('"', 1)[0]
        self.assertEqual(base64.b64decode(encoded), self.ui._load_logo_bytes())

    def test_missing_logo_keeps_text_branding(self):
        with patch("novamind.ui.styles._load_logo_bytes", return_value=None):
            markup = self.ui._brand_html()
        self.assertIn("NovaMind AI", markup)
        self.assertNotIn("<img", markup)

    def test_login_preserves_keys_password_masking_and_submit_callback(self):
        self.ui.load_auth_config = lambda: SimpleNamespace(mode="cognito")
        self.ui._render_login_page()
        inputs = {call.kwargs["key"]: call.kwargs for call in self.st.text_input.call_args_list}
        self.assertIn("login_username_input", inputs)
        self.assertEqual(inputs["login_password_input"]["type"], "password")
        self.assertEqual(self.st.form.call_args.args[0], "login_form")
        submit = self.st.form_submit_button.call_args.kwargs
        self.assertEqual(submit["width"], "stretch")
        self.assertIs(submit["on_click"], self.ui._submit_login)
        self.assertNotIn("Demo credentials", str(self.st.caption.call_args_list))

    def test_sidebar_social_links_and_button_widths(self):
        # Keep settings unchanged while rendering all existing controls.
        self.st.text_area.return_value = self.st.session_state.system_prompt
        self.st.slider.return_value = self.st.session_state.temperature
        self.st.select_slider.return_value = self.st.session_state.max_tokens
        self.ui._render_sidebar()
        links = {call.args[0]: call.args[1] for call in self.st.link_button.call_args_list}
        self.assertEqual(links["GitHub"], "https://github.com/aamir490")
        self.assertEqual(links["LinkedIn"], "https://www.linkedin.com/in/aamir-imran")
        for call in self.st.button.call_args_list:
            self.assertNotIn("use_container_width", call.kwargs)
            self.assertEqual(call.kwargs["width"], "stretch")

    def test_theme_contains_responsive_and_accessible_fallbacks(self):
        self.ui._inject_css()
        css = self.st.markdown.call_args.args[0]
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("focus-visible", css)
        self.assertIn("max-width: 760px", css)
        self.assertIn("height: auto", css)
        self.assertNotIn("@import", css)
