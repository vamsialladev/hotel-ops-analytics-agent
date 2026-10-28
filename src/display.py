"""Text shown with Streamlit markdown. Pure functions, no Streamlit.

Streamlit treats text between two '$' as LaTeX, so "with $768,880. Lodge Queen was second at $647,773" lost both
dollar signs and showed the words between them as math. Every model answer, visitor question and alert goes through
`safe_markdown` ('$' and HTML escaped); our own report files go through `escape_dollars` only, so their tables and
links still render. Same rule as stage 1 (hotel-ops-assistant src/display.py).
"""

import html


def escape_dollars(text: str) -> str:
    return text.replace("\\$", "$").replace("$", "\\$")


def safe_markdown(text: str) -> str:
    """Escape HTML and '$' so model output and visitor input render as plain text."""
    return escape_dollars(html.escape(text or "", quote=False))
