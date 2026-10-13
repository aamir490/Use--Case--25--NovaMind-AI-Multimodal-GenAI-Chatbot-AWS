"""ui / sidebar responsibilities extracted from the Streamlit launcher."""
import html as _html
import streamlit as st
from services.usage_accounting import MODEL_PRICING
from services.request_limits import MODEL_POLICIES
from services.aws_config import REGION
from services.authorization import export_conversation, publish_data, capture_scope
from novamind.config.settings import LANGUAGE_OPTIONS, MODEL_OPTIONS, MODEL_PROVIDERS, PROMPT_TEMPLATES
from novamind.ui.state import _check_aws_connection, _clear_conversation, _model_context_warning, _update_service_settings
from novamind.ui.styles import _brand_html
from novamind.ui.attachments import _render_file_uploader, _render_pending_attachment
from novamind.ui.usage import _render_usage
from services.auth_service import protect_state, logout
from services.conversation_store import (
    enabled as persistence_enabled, list_conversations, load_conversation,
    save_conversation, delete_conversation, PersistenceError,
    conversation_title, has_unsaved_changes,
)
from novamind.domain.navigation import saved_page, set_saved_page


def _render_sidebar() -> None:
    protect_state(st.session_state)
    with st.sidebar:

        st.markdown(_brand_html(compact=True), unsafe_allow_html=True)
        display_identity = st.session_state.auth_session.verified_email or st.session_state.login_user
        st.markdown('<div class="nm-signed-in">Signed in as ' +
                    _html.escape(display_identity) + '</div>', unsafe_allow_html=True)

        # ── Sign out ──────────────────────────────────────────────────────────
        if st.button("🚪 Sign Out", width="stretch"):
            st.session_state["auth_notice"] = logout(st.session_state)
            st.rerun()

        st.divider()

        with st.expander("🧠 Model", expanded=False):
            # ── Model selector ────────────────────────────────────────────────────
            prev_model = st.session_state.selected_model_label
            selected_model = st.selectbox(
                "Select model",
                options=list(MODEL_OPTIONS.keys()),
                index=list(MODEL_OPTIONS.keys()).index(st.session_state.selected_model_label),
                label_visibility="collapsed",
            )
            if selected_model != prev_model:
                st.session_state.selected_model_label = selected_model
                publish_data(st.session_state, bedrock_service=None)   # recreate with new model

            # Show model pricing hint
            mid = MODEL_OPTIONS[selected_model]
            compatibility_warning = _model_context_warning(mid)
            if compatibility_warning:
                st.warning(compatibility_warning)
            policy = MODEL_POLICIES[mid]
            st.caption(f"Local context budget: {policy.context_budget:,} estimated tokens including output. AI memory retains up to 20 recent completed turns and trims older turns when needed.")
            region = REGION
            pricing = MODEL_PRICING.get((region, mid))
            st.caption(
                f"Configured, unverified rates ({region}): ${pricing[0]} / 1K input · ${pricing[1]} / 1K output"
                if pricing else "Pricing unknown for this model and region."
            )

            st.divider()

        with st.expander("✦ Persona & language", expanded=False):
            # ── Prompt templates ──────────────────────────────────────────────────
            prev_template = st.session_state.selected_template
            selected_template = st.selectbox(
                "Choose a prompt template",
                options=list(PROMPT_TEMPLATES.keys()),
                index=list(PROMPT_TEMPLATES.keys()).index(st.session_state.selected_template),
                label_visibility="collapsed",
            )
            if selected_template != prev_template:
                st.session_state.selected_template = selected_template
                st.session_state.system_prompt     = PROMPT_TEMPLATES[selected_template]
                _update_service_settings()

            # Custom system prompt override
            with st.container(border=True):
                st.markdown("**Custom system prompt**")
                custom_prompt = st.text_area(
                    "System prompt",
                    value=st.session_state.system_prompt,
                    height=110,
                    label_visibility="collapsed",
                )
                if st.button("Apply", width="stretch"):
                    st.session_state.system_prompt = custom_prompt
                    _update_service_settings()
                    st.success("Updated.")

            st.divider()

            # ── Language selector ─────────────────────────────────────────────────
            prev_lang = st.session_state.selected_language
            selected_language = st.selectbox(
                "Language",
                options=list(LANGUAGE_OPTIONS.keys()),
                index=list(LANGUAGE_OPTIONS.keys()).index(st.session_state.selected_language),
                label_visibility="collapsed",
            )
            if selected_language != prev_lang:
                st.session_state.selected_language = selected_language
                _update_service_settings()

            st.divider()

        with st.expander("⚙️ Response settings", expanded=False):
            # ── Inference settings ────────────────────────────────────────────────
            temperature = st.slider(
                "Temperature",
                min_value=0.0, max_value=1.0,
                value=st.session_state.temperature,
                step=0.05,
            )
            max_tokens = st.select_slider(
                "Max response tokens",
                options=sorted({256, 512, 1024, 2048, 4096, 8192, st.session_state.max_tokens}),
                value=st.session_state.max_tokens,
            )
            if temperature != st.session_state.temperature or max_tokens != st.session_state.max_tokens:
                st.session_state.temperature = temperature
                st.session_state.max_tokens  = max_tokens
                _update_service_settings()

            st.divider()

        with st.expander("📎 Attach a file", expanded=False):
            # ── File upload ───────────────────────────────────────────────────────
            st.markdown(
                '<div class="nm-upload-info">'
                "📷 <b>Images:</b> JPEG, PNG, GIF, WebP (max 3.75 MB)<br>"
                "📄 <b>Documents:</b> PDF, TXT, MD, CSV, DOCX, XLSX, HTML (max 4.5 MB)"
                "</div>",
                unsafe_allow_html=True,
            )
            _render_file_uploader()
            _render_pending_attachment()

            st.divider()

        with st.expander("💬 Conversation", expanded=True):
            # ── Conversation actions ──────────────────────────────────────────────
            st.text(conversation_title(st.session_state))
            dirty = has_unsaved_changes(st.session_state)
            st.caption("Unsaved changes" if dirty else
                       ("Saved conversation" if st.session_state.persistence_version else "New chat"))
            st.caption("Clear and New reset this local chat. Saved copies remain available below.")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ Clear", width="stretch"):
                    _clear_conversation()
                    st.rerun()
            with col2:
                if st.button("🔄 New", width="stretch"):
                    _clear_conversation()
                    st.session_state.conversation_count += 1
                    st.rerun()

            if persistence_enabled() and st.session_state.auth_session.config.mode == "cognito":
                if st.button("Save conversation", width="stretch"):
                    try:
                        save_conversation(st.session_state)
                        set_saved_page(st.session_state, list_conversations(st.session_state))
                        dirty = has_unsaved_changes(st.session_state)
                        st.success("Conversation saved.")
                    except PersistenceError as exc:
                        st.warning(str(exc))
                if st.button("Browse saved conversations", width="stretch"):
                    try:
                        set_saved_page(st.session_state, list_conversations(st.session_state))
                    except PersistenceError as exc:
                        st.warning(str(exc))
                page = saved_page(st.session_state)
                saved = page.get("items", [])
                if saved:
                    labels = {row["conversation_id"]: row["title"] for row in saved}
                    selected_id = st.selectbox("Saved conversations", list(labels),
                                               index=list(labels).index(st.session_state.conversation_id)
                                               if st.session_state.conversation_id in labels else 0,
                                               key="saved_chat_" + st.session_state.conversation_id,
                                               format_func=lambda value: labels[value] + " · " + value[:8] +
                                               (" (current)" if value == st.session_state.conversation_id else ""))
                    discard = not dirty or st.checkbox("Discard unsaved changes when loading",
                                                       key="discard_chat_" + st.session_state.conversation_id +
                                                       "_" + str(st.session_state.upload_generation))
                    if st.button("Load selected conversation", width="stretch", disabled=not discard) and discard:
                        try:
                            load_conversation(st.session_state, selected_id)
                            st.rerun()
                        except PersistenceError as exc:
                            st.warning(str(exc))
                    allow_delete = selected_id != st.session_state.conversation_id or discard
                    if st.button("Delete selected saved conversation", width="stretch",
                                 disabled=not allow_delete) and allow_delete:
                        try:
                            delete_conversation(st.session_state, selected_id)
                            if selected_id == st.session_state.conversation_id:
                                _clear_conversation()
                            set_saved_page(st.session_state, list_conversations(st.session_state))
                            st.rerun()
                        except PersistenceError as exc:
                            st.warning(str(exc))
                if page.get("next_key") and st.button("More saved conversations", width="stretch"):
                    try:
                        set_saved_page(st.session_state, list_conversations(
                            st.session_state, start_key=page["next_key"]), append=True)
                        st.rerun()
                    except PersistenceError as exc:
                        st.warning(str(exc))
                if not saved:
                    st.caption("Browse saved conversations to see your chats. Save this chat to add it.")
                elif len(saved) >= 100:
                    st.caption("Showing up to 100 saved chats. Browse again to refresh.")

            # Summary button
            if st.session_state.chat_history:
                if st.button("📝 Summarise conversation", width="stretch"):
                    st.session_state._trigger_summary = True

            # Keep private transcripts inside the authenticated WebSocket response.
            # Streamlit download_button publishes a separately served media URL.
            if st.session_state.chat_history:
                if st.button("📋 Export transcript", width="stretch"):
                    transcript = export_conversation(st.session_state)
                    st.code(transcript, language=None)
                    st.caption("Copy this transcript to save it locally.")

            msg_count = len(st.session_state.chat_history)
            if msg_count:
                turns = msg_count // 2
                st.caption(f"💬 {msg_count} messages · {turns} turn{'s' if turns != 1 else ''}")

            st.divider()

            # ── Token & cost counter ──────────────────────────────────────────────
            _render_usage()

            st.divider()

        # ── Provider connection check ─────────────────────────────────────────
        selected_model_id = MODEL_OPTIONS[st.session_state.selected_model_label]
        selected_provider = MODEL_PROVIDERS[selected_model_id]
        provider_name = "Groq Cloud" if selected_provider == "groq" else "Bedrock"
        st.markdown(f"### 🔌 {provider_name} Connection" if selected_provider == "groq" else "### 🔌 AWS Connection")
        check_label = (f"🔍 Run live {provider_name} check (uses tokens)" if selected_provider == "groq"
                       else "🔍 Run live Bedrock check (uses tokens)")
        if st.button(check_label, width="stretch"):
            with st.spinner(f"Checking {provider_name}..." if selected_provider == "groq" else "Pinging Bedrock..."):
                scope = capture_scope(st.session_state)
                status = _check_aws_connection(live=True)
                publish_data(st.session_state, expected=scope, aws_status=status)

        if st.session_state.aws_status:
            s = st.session_state.aws_status
            if s["ok"]:
                st.markdown(
                    f'<p class="nm-status-ok">✅ Connected — {s["latency_ms"]} ms</p>'
                    f'<div style="font-size:0.74rem; color:#484f58;">'
                    (f'Model: {_html.escape(s["model"])}<br>Provider: Groq Cloud</div>'
                     if selected_provider == "groq" else
                     f'Model: {_html.escape(s["model"])}<br>Region: {_html.escape(s["region"])}</div>'),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<p class="nm-status-err">❌ Connection failed</p>'
                    f'<div style="font-size:0.74rem; color:#f85149;">{_html.escape(s["error"])}</div>',
                    unsafe_allow_html=True,
                )

        st.divider()

        # ── Model info card ───────────────────────────────────────────────────
        svc      = st.session_state.bedrock_service
        model_id = MODEL_OPTIONS[st.session_state.selected_model_label]
        region   = REGION
        if svc:
            region = svc.region
        st.markdown(
            f'<div class="nm-model-card">'
            f'<strong>Model</strong> {model_id}<br>'
            f'<strong>Region</strong> {region}<br>'
            f'<strong>Temp</strong> {st.session_state.temperature} &nbsp;'
            f'<strong>MaxTok</strong> {st.session_state.max_tokens}<br>'
            f'<strong>Lang</strong> {st.session_state.selected_language}'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown('<div class="nm-sidebar-footer">Built By Aamir</div>', unsafe_allow_html=True)
        github, linkedin = st.columns(2)
        with github:
            st.link_button("GitHub", "https://github.com/aamir490", icon=":material/code:", width="stretch")
        with linkedin:
            st.link_button("LinkedIn", "https://www.linkedin.com/in/aamir-imran", icon=":material/work:", width="stretch")
