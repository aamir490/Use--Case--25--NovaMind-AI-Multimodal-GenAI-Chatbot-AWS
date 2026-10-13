"""Private previews travel inline, never through a public Streamlit media URL."""
import base64
import streamlit as st
from services.auth_service import protect_state


def render_private_thumbnail(data):
    protect_state(st.session_state)
    encoded = base64.b64encode(data).decode("ascii")
    # ImageService produces PNG thumbnails. No filenames or document text enter
    # this HTML; base64 has no markup characters.
    st.markdown(f'<img src="data:image/png;base64,{encoded}" alt="Image preview" '
                'style="max-width:100%;width:280px;height:auto;"/>', unsafe_allow_html=True)
