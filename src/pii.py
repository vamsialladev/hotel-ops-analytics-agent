"""Personal-data redaction before storage (Project 4). Applied to every log record (requests, feedback, errors)
before it is written to a file or the database, after secrets are masked (usage.redact).

    emails            -> [email]
    phone numbers     -> [phone]
    card-like numbers -> [card]        13-19 digits, spaces or dashes allowed
    booking IDs       -> BK-1a2b3c4d   stable hash: the same booking keeps the same pseudonym across records
    names             -> [name]        sign-offs, "my name is ...", "Mr/Ms/Dr ...", "guest named ...", greetings,
                                       and known names passed in (Project 2: the sender's name)

Deterministic and conservative (regular expressions, no model, no API). It cannot catch every name in free text:
this is listed under Known limitations in SECURITY.md, and tests/test_pii.py plants personal data in every field
of a real record and fails if any of it survives.
"""

import hashlib
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
PHONE = re.compile(r"(?<![\w$.,:])(?:\+?\d{1,3}[ -]?)?(?:\(\d{2,4}\)|\d{2,4})[ -]?\d{3,4}[ -]?\d{3,4}(?![\w.,]?\d)")
BOOKING = re.compile(r"\b(?:BR|ML)-\d{3,5}\b", re.I)
NAME = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ'’-]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ'’-]+){0,2}"
NAME_CONTEXT = re.compile(
    rf"(?P<lead>\b(?i:my name is|this is|i am|i'm|me llamo|soy|mi nombre es|guest named|guest called|"
    rf"(?:Mr|Mrs|Ms|Miss|Dr|Sr|Sra|Srta)\.?|(?:Hi|Hello|Dear|Hola|Estimado|Estimada|Estimado/a)[ \t]*,?)"
    rf"[ \t]+)(?P<name>{NAME})"
)
# The last line(s) of an email: "Thanks,\nPriya" / "Gracias,\nLucía Romero" / "Best regards,\nOwen Clarke"
SIGN_OFF = re.compile(
    rf"(?P<lead>\b(?i:thanks|thank you|cheers|regards|best regards|best|kind regards|many thanks|gracias|saludos|"
    rf"un saludo|atentamente)\s*[,!.]?\s*\n+\s*)(?P<name>{NAME})"
)
SAFE_WORDS = {
    "Guest",
    "Services",
    "Guest Services",
    "Beach",
    "Resort",
    "Mountain",
    "Lodge",
    "Front",
    "Desk",
    "Team",
    "Gold",
    "Silver",
    "Platinum",
    "Member",
    "Manager",
    "Staff",
    "Here",
    "Sorry",
}


def booking_pseudonym(booking_id: str) -> str:
    return "BK-" + hashlib.sha256(booking_id.upper().encode()).hexdigest()[:8]


def _name_sub(match: re.Match) -> str:
    name = match.group("name")
    if name in SAFE_WORDS or name.split()[0] in SAFE_WORDS:
        return match.group(0)
    return match.group("lead") + "[name]"


def scrub_text(text: str, names: tuple[str, ...] = ()) -> str:
    text = EMAIL.sub("[email]", text)
    text = CARD.sub("[card]", text)
    text = PHONE.sub("[phone]", text)
    text = BOOKING.sub(lambda m: booking_pseudonym(m.group(0)), text)
    for name in sorted({n.strip() for n in names if n and len(n.strip()) > 1}, key=len, reverse=True):
        for part in [name, *name.split()]:
            if len(part) > 2:
                text = re.sub(rf"\b{re.escape(part)}\b", "[name]", text)
    text = NAME_CONTEXT.sub(_name_sub, text)
    return SIGN_OFF.sub(_name_sub, text)


# Fields that are personal data as a whole (Project 2 records the sender): replaced, not pattern-matched.
WHOLE_FIELDS = {
    "sender": "[email]",
    "from": "[email]",
    "sender_email": "[email]",
    "sender_name": "[name]",
    "name": "[name]",
    "guest_name": "[name]",
    "member_number": "[member]",
}
KEEP_FIELDS = {
    "request_id",
    "turn_id",
    "session_id",
    "time",
    "ts",
    "schema_version",
    "model",
    "property",
    "outcome",
    "kind",
    "source",
    "mode",
    "error",
    "page",
    "code",
    "category",
}


def scrub(value, names: tuple[str, ...] = (), key: str | None = None):
    """Copy of a record with personal data removed from every string, at any depth."""
    if key in WHOLE_FIELDS and isinstance(value, str) and value:
        return WHOLE_FIELDS[key]
    if key in KEEP_FIELDS:
        return value
    if isinstance(value, str):
        return scrub_text(value, names)
    if isinstance(value, dict):
        return {k: scrub(v, names, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v, names) for v in value]
    return value


def known_names(record: dict) -> tuple[str, ...]:
    """Names the record itself reveals (sender, guest name on a booking), masked wherever else they appear."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("sender_name", "name", "guest_name") and isinstance(v, str):
                    found.append(v)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(record)
    return tuple(found)


def redact_record(record: dict) -> dict:
    return scrub(record, known_names(record))
