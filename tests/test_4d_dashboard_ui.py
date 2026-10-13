"""Verified identity presentation and accessible dashboard section smoke tests."""
import unittest

import test_3a_cognito_auth as auth_fixtures
from tests.frontend_support import load_frontend
from tests.offline_support import offline_environment
from unittest.mock import MagicMock


class TestDashboardUX(auth_fixtures.TestCognitoAuth):
    def test_only_verified_cognito_email_is_exposed_for_display(self):
        self.client.get_user.return_value = {
            "Username": "alice", "UserAttributes": [
                {"Name": "sub", "Value": "subject-1"},
                {"Name": "email", "Value": "alice@example.com"},
                {"Name": "email_verified", "Value": "true"},
            ]}
        session = self.sign_in()
        self.assertEqual(session.verified_email, "alice@example.com")

    def test_unverified_or_duplicate_email_falls_back_to_username(self):
        for attrs in (
            [{"Name": "email", "Value": "alice@example.com"},
             {"Name": "email_verified", "Value": "false"}],
            [{"Name": "email", "Value": "alice@example.com"},
             {"Name": "email", "Value": "other@example.com"},
             {"Name": "email_verified", "Value": "true"}],
        ):
            self.client.get_user.return_value = {
                "Username": "alice", "UserAttributes": [
                    {"Name": "sub", "Value": "subject-1"}, *attrs]}
            self.assertEqual(self.sign_in().verified_email, "")

    def test_collapsible_sidebar_keeps_existing_widget_labels_and_keys(self):
        self.enterContext(offline_environment())
        st = MagicMock()
        st.session_state = auth_fixtures.State()
        st.columns.side_effect = lambda spec, **kw: [
            MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
        st.button.return_value = False
        st.selectbox.side_effect = lambda label, options, **kw: list(options)[kw.get("index", 0)]
        ui = load_frontend(st, self)
        ui._init_session_state()
        st.text_area.return_value = st.session_state.system_prompt
        st.slider.return_value = st.session_state.temperature
        st.select_slider.return_value = st.session_state.max_tokens
        st.session_state.auth_session.verified_email = "alice@example.com"
        st.session_state["login_user"] = "alice"
        ui._render_sidebar()
        self.assertIn("alice@example.com", " ".join(
            str(call.args[0]) for call in st.markdown.call_args_list if call.args))
        expanders = [call.args[0] for call in st.expander.call_args_list]
        self.assertTrue(any("Persona & language" in label for label in expanders))
        self.assertTrue(any("Attach a file" in label for label in expanders))
        self.assertTrue(any("Conversation" in label for label in expanders))
        self.assertEqual([call.args[0] for call in st.selectbox.call_args_list[:3]],
                         ["Select model", "Choose a prompt template", "Language"])
        self.assertEqual(st.file_uploader.call_args.kwargs["key"], ui._upload_widget_key())

