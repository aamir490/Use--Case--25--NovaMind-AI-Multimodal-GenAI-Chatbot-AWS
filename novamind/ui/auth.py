"""ui / auth responsibilities extracted from the Streamlit launcher."""
import streamlit as st
from services.auth_service import (
    load_auth_config, login, complete_mfa, require_session, clear_session,
    AuthenticationError,
)
from services.aws_config import AWSConfigurationError
from novamind.ui.styles import _inject_css, _brand_html


def _render_login_page() -> None:
    """Render login without exposing demo credentials in Cognito mode."""
    try:
        config = load_auth_config()
    except AWSConfigurationError as exc:
        st.error(str(exc))
        return
    notice = st.session_state.pop("auth_notice", None)
    if notice:
        st.info(notice)
    _inject_css()

    left_col, right_col = st.columns([1.15, 1], gap="large")
    with left_col:
        st.markdown(_brand_html(), unsafe_allow_html=True)
        st.markdown("""
        <div class="nm-info-card">
          <div class="nm-eyebrow">YOUR AI WORKSPACE</div>
          <h1>Ideas into answers.</h1>
          <p>One calm workspace for conversations, images and documents.</p>
          <div class="nm-feat-row"><span aria-hidden="true">✦</span>
            <div><strong>Conversations that connect</strong><br>Streaming answers with recent conversation memory.</div></div>
          <div class="nm-feat-row"><span aria-hidden="true">▧</span>
            <div><strong>Bring your files</strong><br>Explore images and ask questions about documents.</div></div>
          <div class="nm-feat-row"><span aria-hidden="true">↗</span>
            <div><strong>Pick your perspective</strong><br>Switch models and response languages in your workspace.</div></div>
        </div>
        """, unsafe_allow_html=True)

    with right_col:
        st.markdown("""
        <div class="nm-form-card">
          <div class="nm-form-title">Welcome back</div>
          <div class="nm-form-sub">Sign in to your NovaMind AI workspace</div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.get("auth_challenge"):
            with st.form("cognito_mfa", clear_on_submit=True):
                st.text_input("Verification code", key="login_mfa_input", type="password", max_chars=6)
                st.form_submit_button("Verify", on_click=_submit_mfa, width="stretch")
            if st.button("Cancel sign in"):
                clear_session(st.session_state)
                st.rerun()
        else:
            with st.form("login_form", clear_on_submit=True):
                st.text_input("Username", placeholder="Enter username", key="login_username_input", max_chars=128)
                st.text_input("Password", type="password", placeholder="Enter password",
                              key="login_password_input", max_chars=256)
                st.form_submit_button("🔐  Sign In", on_click=_submit_login, width="stretch")
        if config.mode == "demo":
            st.warning("Local demo authentication only. Bind this server to 127.0.0.1.")
            st.caption("Demo credentials: demo / demo1234")
        else:
            st.caption("Sign in with your Cognito account. Contact your administrator for account setup or recovery.")


def _submit_login():
    # Callbacks execute before the next render, so widget secrets can be removed.
    username = st.session_state.pop("login_username_input", "")
    password = st.session_state.pop("login_password_input", "")
    try:
        login(st.session_state, username, password)
    except (AuthenticationError, AWSConfigurationError) as exc:
        clear_session(st.session_state)
        st.session_state["auth_notice"] = str(exc)


def _submit_mfa():
    code = st.session_state.pop("login_mfa_input", "")
    try:
        complete_mfa(st.session_state, code)
    except (AuthenticationError, AWSConfigurationError) as exc:
        clear_session(st.session_state)
        st.session_state["auth_notice"] = str(exc)


def _check_login() -> bool:
    """The compatibility Boolean is never sufficient to authenticate a session."""
    try:
        load_auth_config()
        if "auth_session" not in st.session_state:
            if any(key in st.session_state for key in ("chat_history", "bedrock_history", "data_owner")):
                clear_session(st.session_state)
            st.session_state["logged_in"] = False
            st.session_state["login_user"] = ""
            return False
        session = require_session(st.session_state, touch=True)
        st.session_state["logged_in"] = True
        st.session_state["login_user"] = session.username
        return True
    except (AuthenticationError, AWSConfigurationError) as exc:
        clear_session(st.session_state)
        st.session_state["auth_notice"] = str(exc)
        return False


@st.fragment(run_every="30s")
def _session_watchdog():
    """Expire an idle visible page without extending its activity timestamp."""
    if "auth_session" not in st.session_state:
        return
    try:
        require_session(st.session_state)
    except (AuthenticationError, AWSConfigurationError) as exc:
        clear_session(st.session_state)
        st.session_state["auth_notice"] = str(exc)
        st.rerun(scope="app")
