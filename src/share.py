"""'Share this conversation': a read-only link with the conversation inside the URL. Nothing is stored on a server.

Each turn (question, how it was understood, answer, SQL, source tables) is JSON, zlib-compressed and
base64url-encoded into `?share=...`. Personal data is checked first with the same redaction as the logs
(src/pii.py), including guest names a manager's query returned; anything found is replaced in the shared copy and
the visitor is told what was replaced. Result rows are never shared. Opening a link only decodes and displays it;
it never calls the API or runs SQL.
"""

import base64
import binascii
import json
import zlib

from src.pii import scrub_text

VERSION = 1
MAX_TURNS = 10
MAX_TEXT = 1200
MAX_TOKEN = 8000
FINDINGS = {"[email]": "an email address", "[phone]": "a phone number", "[card]": "a card number", "[name]": "a name"}
FIELDS = ("q", "u", "a", "sql")


def turn_payload(turn: dict) -> dict:
    return {
        "q": (turn.get("question") or "")[:MAX_TEXT],
        "u": (turn.get("understood_as") or "")[:MAX_TEXT],
        "a": (turn.get("answer") or turn.get("message") or "")[:MAX_TEXT],
        "sql": (turn.get("sql") or "")[:MAX_TEXT],
        "t": [str(t) for t in turn.get("tables", [])][:12],
    }


def redact(turns: list[dict], names: tuple[str, ...] = ()) -> tuple[list[dict], list[str]]:
    found, out = set(), []
    for t in turns:
        clean = dict(t)
        for key in FIELDS:
            original = t.get(key) or ""
            scrubbed = scrub_text(original, names)
            found |= {label for marker, label in FINDINGS.items() if marker in scrubbed and marker not in original}
            clean[key] = scrubbed
        out.append(clean)
    return out, sorted(found)


def encode(payload: list[dict]) -> str:
    raw = json.dumps({"v": VERSION, "t": payload}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def make_token(turns: list[dict], names: tuple[str, ...] = ()) -> tuple[str | None, list[str]]:
    payload, found = redact([turn_payload(t) for t in turns][-MAX_TURNS:], names)
    while payload:
        token = encode(payload)
        if len(token) <= MAX_TOKEN:
            return token, found
        payload = payload[1:]
    return None, found


def decode(token: str) -> list[dict] | None:
    if not token or len(token) > MAX_TOKEN:
        return None
    try:
        raw = zlib.decompressobj().decompress(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)), 200_000)
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, binascii.Error, zlib.error, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("v") != VERSION or not isinstance(data.get("t"), list):
        return None
    turns = []
    for t in data["t"][:MAX_TURNS]:
        if not isinstance(t, dict) or not isinstance(t.get("q"), str) or not isinstance(t.get("a"), str):
            return None
        turns.append(
            {
                "q": t["q"][:MAX_TEXT],
                "u": str(t.get("u") or "")[:MAX_TEXT],
                "a": t["a"][:MAX_TEXT],
                "sql": str(t.get("sql") or "")[:MAX_TEXT],
                "t": [str(x)[:40] for x in t.get("t", []) if isinstance(x, str)][:12],
            }
        )
    return turns or None


def share_url(base_url: str, token: str) -> str:
    base = (base_url or "").split("?", 1)[0].split("#", 1)[0]
    return f"{base}?share={token}"
