"""A stand-in for the Anthropic client: queued replies, recorded requests, no network."""

import json
from contextlib import contextmanager
from types import SimpleNamespace


def _usage():
    return SimpleNamespace(input_tokens=100, output_tokens=20)


class FakeClient:
    """`create` returns the queued replies in order (dicts become JSON text, strings stay text); `stream` streams
    the queued answer text in two chunks."""

    def __init__(self, *replies, answer="Beach Resort had 4,347 bookings and Mountain Lodge 3,182."):
        self.replies, self.requests, self.answer = list(replies), [], answer
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=_usage())

    @contextmanager
    def stream(self, **request):
        self.requests.append(request)
        half = len(self.answer) // 2
        yield SimpleNamespace(
            text_stream=iter([self.answer[:half], self.answer[half:]]),
            get_final_message=lambda: SimpleNamespace(usage=_usage()),
        )


def plan(action="sql", sql="", message="m", chart="none", x="", y=""):
    return {"action": action, "message": message, "sql": sql, "chart": chart, "x": x, "y": y}
