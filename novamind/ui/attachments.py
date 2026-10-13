"""ui / attachments responsibilities extracted from the Streamlit launcher."""
import html as _html
import streamlit as st
from novamind.ui.state import _handle_file_upload, _on_upload_changed, _reset_attachment, _upload_widget_key
from services.auth_service import protect_state
from novamind.ui.private_media import render_private_thumbnail


def _render_file_uploader() -> None:
    protect_state(st.session_state)
    key = _upload_widget_key()
    uploaded_file = st.file_uploader(
        "Upload",
        type=["jpg","jpeg","png","gif","webp","pdf","txt","md","csv",
              "doc","docx","xls","xlsx","html","htm"],
        label_visibility="collapsed", key=key,
        on_change=_on_upload_changed, args=(key,),
    )
    # Synchronize even when empty (including the uploader's native remove X).
    # Callback + normal rerun share the same cached validation result.
    _handle_file_upload(uploaded_file)


def _render_pending_attachment() -> None:
    protect_state(st.session_state)
    if st.session_state.upload_error:
        st.error(f"❌ {st.session_state.upload_error}")
    img = st.session_state.pending_image
    doc = st.session_state.pending_document

    if img:
        st.markdown(
            f'<div class="nm-attachment">'
            f'🖼️ <span class="nm-badge-image">IMAGE</span> {_html.escape(img.file_name)} · {img.size_kb} KB'
            f'</div>',
            unsafe_allow_html=True,
        )
        if img.thumbnail_bytes:
            render_private_thumbnail(img.thumbnail_bytes)
            st.caption(img.dimensions)
        if st.button("✕ Remove image", width="stretch"):
            _reset_attachment()
            st.rerun()

    elif doc:
        st.markdown(
            f'<div class="nm-attachment">'
            f'📄 <span class="nm-badge-document">DOC</span> {_html.escape(doc.file_name)} · {doc.size_kb} KB'
            f'</div>',
            unsafe_allow_html=True,
        )
        if doc.preview_text:
            with st.expander("Preview extracted text", expanded=False):
                # preview_text comes from document bytes (PDF, CSV, etc.) — must be escaped
                st.markdown(
                    f'<div class="nm-preview">{_html.escape(doc.preview_text)}</div>',
                    unsafe_allow_html=True,
                )
        if st.button("✕ Remove document", width="stretch"):
            _reset_attachment()
            st.rerun()
