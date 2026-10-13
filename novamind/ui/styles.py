"""Shared presentation styles and deployment-safe local branding."""
import base64
from pathlib import Path
import streamlit as st
from novamind.config.settings import ROOT


def _load_logo_bytes() -> bytes | None:
    """Resolve the bundled PNG from the project root, independent of cwd."""
    try:
        return (ROOT / "novamind-logo.png").read_bytes()
    except OSError:
        return None


def _brand_html(*, compact=False) -> str:
    logo = _load_logo_bytes()
    image = (f'<img src="data:image/png;base64,{base64.b64encode(logo).decode()}" '
             'alt="NovaMind AI logo" class="nm-brand-logo" />') if logo else ""
    variant = " nm-brand-compact" if compact else ""
    byline = "" if compact else '<div class="nm-brand-byline">Built By Aamir</div>'
    heading_level = "2" if compact else "1"
    return (f'<div class="nm-brand{variant}">{image}<div>'
            f'<div class="nm-brand-title" role="heading" aria-level="{heading_level}">NovaMind AI</div>'
            f'{byline}</div></div>')


def _inject_css() -> None:
    css = Path(__file__).with_name("theme.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
