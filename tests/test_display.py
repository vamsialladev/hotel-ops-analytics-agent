"""Dollar amounts and visitor text must render as written, not as LaTeX or HTML."""

from src import display


def test_two_dollar_amounts_are_escaped():
    text = "Cabin earned $768,880. Lodge Queen was second at $647,773."
    assert display.safe_markdown(text) == "Cabin earned \\$768,880. Lodge Queen was second at \\$647,773."


def test_escaping_twice_does_not_double_the_backslash():
    once = display.escape_dollars("priced $50 vs $515")
    assert display.escape_dollars(once) == once


def test_html_in_visitor_text_is_shown_as_text():
    assert display.safe_markdown("<script>alert(1)</script> $5") == "&lt;script&gt;alert(1)&lt;/script&gt; \\$5"


def test_streamed_chunks_escape_the_same_as_the_whole_answer():
    answer = "Revenue was $1,313,361 and $1,269,551."
    chunks = [answer[i : i + 3] for i in range(0, len(answer), 3)]
    assert "".join(display.safe_markdown(c) for c in chunks) == display.safe_markdown(answer)


def test_empty_text():
    assert display.safe_markdown("") == ""
    assert display.safe_markdown(None) == ""
