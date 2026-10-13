"""ui / app responsibilities extracted from the Streamlit launcher."""
import html as _html
import streamlit as st
from novamind.config.settings import MODEL_OPTIONS, MODEL_PROVIDERS
from services.aws_config import safe_aws_error, AWSConfigurationError
from novamind.ui.auth import _check_login, _render_login_page, _session_watchdog
from novamind.ui.chat import _handle_summary, _handle_user_input, _render_chat_history, _render_welcome
from novamind.ui.state import _init_session_state
from novamind.ui.styles import _inject_css, _brand_html
from novamind.ui.sidebar import _render_sidebar
from novamind.ui.live_metrics import render_live_metrics
from services.auth_service import AuthenticationError, clear_session
from services.authorization import AuthorizationError


def configure_page() -> None:
    st.set_page_config(
        page_title="NovaMind AI",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get Help": "https://docs.aws.amazon.com/bedrock/",
            "About": "NovaMind AI — Multimodal chatbot powered by Amazon Nova Pro on AWS Bedrock.",
        },
    )


def main() -> None:
    configure_page()
    _inject_css()
    try:
        _run_app()
    except AuthorizationError:
        # A stale operation must not erase a newer valid conversation/login.
        # Invalid/tampered states are already cleared by require_session.
        st.rerun()
    except (AuthenticationError, AWSConfigurationError) as exc:
        clear_session(st.session_state)
        st.session_state["auth_notice"] = str(exc)
        # A fresh render removes sidebar/history already emitted by this run.
        st.rerun()


def _run_app() -> None:

    # ── Auth gate ─────────────────────────────────────────────────────────────
    if not _check_login():
        _render_login_page()
        return
    _session_watchdog()

    # ── Init state ────────────────────────────────────────────────────────────
    try:
        _init_session_state()
    except AWSConfigurationError as exc:
        st.error(safe_aws_error(exc))
        return

    # ── Sidebar ───────────────────────────────────────────────────────────────
    _render_sidebar()

    # ── Handle summary trigger (set by sidebar button) ────────────────────────
    if st.session_state.get("_trigger_summary"):
        st.session_state._trigger_summary = False
        _handle_summary()
        st.rerun()

    # ── Hero header ───────────────────────────────────────────────────────────
    bot_name    = st.session_state.bot_name
    pending_img = st.session_state.pending_image
    pending_doc = st.session_state.pending_document
    model_label = st.session_state.selected_model_label.split("(")[0].strip()
    model_id = MODEL_OPTIONS[st.session_state.selected_model_label]
    provider_label = "Groq Cloud" if MODEL_PROVIDERS[model_id] == "groq" else "Amazon Bedrock"
    display_identity = st.session_state.auth_session.verified_email or st.session_state.login_user

    if pending_img:
        sub = (f"<span class='nm-meta-highlight'>Image attached</span> · "
               f"{_html.escape(pending_img.file_name)} · Type your question below")
    elif pending_doc:
        sub = (f"<span class='nm-meta-highlight'>Document attached</span> · "
               f"{_html.escape(pending_doc.file_name)} · Type your question below")
    else:
        sub = (
            f"<span>{_html.escape(model_label)}</span> · "
            f"<span>{_html.escape(st.session_state.selected_language)}</span> · "
            f"<span>{_html.escape(provider_label)}</span> · "
            f"<span>{_html.escape(display_identity)}</span>"
        )

    st.markdown(
        f"""<div class="nm-hero">
            {_brand_html()}
            <p>{sub}</p>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown(render_live_metrics(st.session_state), unsafe_allow_html=True)

    # ── Chat area ─────────────────────────────────────────────────────────────
    if st.session_state.chat_history:
        _render_chat_history()
    else:
        _render_welcome()

    # ── Chat input ────────────────────────────────────────────────────────────
    if pending_img:
        placeholder = f"Ask {bot_name} about the attached image..."
    elif pending_doc:
        placeholder = f"Ask {bot_name} about the attached document..."
    else:
        placeholder = f"Ask {bot_name} anything..."

    user_input = st.chat_input(placeholder)
    if user_input:
        if _handle_user_input(user_input):
            st.rerun()
