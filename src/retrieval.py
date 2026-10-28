"""Retrieve the schema docs and metric definitions a question needs, so the SQL is written from cited sources.

The documents are the table descriptions and the agreed metric definitions in src/schema.py: one document per
table and one per definition. BM25 (no model, no API) scores them against the question; each definition names the
tables it uses, and those table docs come with it. The plan prompt then contains only the retrieved documents, and
the answer lists them as its sources next to the tables the SQL actually read.

The free retrieval eval (python -m eval.run_eval --retrieval) checks that, for every labelled question, the
retrieved table docs cover every table the reference SQL reads.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from src import schema

WORD = re.compile(r"[a-z0-9]+")
STOP = {
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or", "by", "is", "was", "were", "what", "which",
    "how", "many", "much", "did", "do", "does", "we", "our", "us", "me", "show", "give", "list", "per", "each", "with",
    "from", "this", "that", "it", "be", "are", "has", "have", "had", "there", "their", "than", "most", "least",
}  # fmt: skip
ALWAYS = ("def:dates", "def:bookings")  # rules that change almost every count: they come with every question
# Words managers use that the schema spells differently.
SYNONYMS = {
    "revenue": "total_usd sum revenue",
    "earned": "revenue total_usd",
    "earn": "revenue total_usd",
    "made": "revenue",
    "sales": "revenue",
    "money": "revenue total_usd",
    "occupancy": "occupancy rooms_count check_in check_out",
    "occupied": "occupancy",
    "full": "occupancy",
    "cancellation": "cancelled status cancellation",
    "cancel": "cancelled status",
    "adr": "adr rate revenue nights",
    "price": "rate_usd price_usd",
    "rate": "rate rate_usd",
    "refund": "refunds amount_usd reason",
    "refunded": "refunds amount_usd",
    "complaint": "feedback score comment refunds",
    "review": "feedback score comment",
    "rating": "feedback score",
    "satisfaction": "feedback score",
    "spa": "activities activity_bookings",
    "club": "activities activity_bookings",
    "kids": "activities activity_bookings",
    "party": "party_size activity_bookings",
    "activity": "activities activity_bookings",
    "tour": "activities activity_bookings",
    "noshow": "no_show activity_bookings",
    "loyalty": "loyalty_tier guests",
    "member": "loyalty_tier guests",
    "gold": "loyalty_tier guests",
    "platinum": "loyalty_tier guests",
    "silver": "loyalty_tier guests",
    "guest": "guests",
    "country": "country guests",
    "channel": "channel bookings direct ota",
    "ota": "channel ota",
    "direct": "channel direct",
    "room": "rooms room_type",
    "suite": "rooms room_type rates",
    "cabin": "rooms room_type rates",
    "night": "nights room_nights",
    "stay": "nights bookings",
    "lead": "booked_at check_in lead",
    "advance": "booked_at check_in",
    "email": "email guests",
    "phone": "phone guests",
    "name": "full_name guests",
}
K_DEFINITIONS = 3
K_TABLES = 4


@dataclass(frozen=True)
class Doc:
    id: str  # "table:bookings" or "def:revenue"
    title: str
    text: str
    tables: tuple[str, ...]  # the table docs this one brings with it


def stem(word: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def tokens(text: str) -> list[str]:
    raw = WORD.findall(text.lower().replace("no-show", "noshow").replace("no_show", "noshow"))
    out = []
    for w in raw:
        if w in STOP:
            continue
        out.append(stem(w))
        out += [stem(s) for s in WORD.findall(SYNONYMS.get(w, SYNONYMS.get(stem(w), "")))]
    return out


def documents() -> list[Doc]:
    docs = [
        Doc(f"table:{name}", f"Table {name}", f"Table {name}: {cols}", (name, *schema.JOINS.get(name, ())))
        for name, cols in schema.TABLES.items()
    ]
    docs += [Doc(f"def:{d['id']}", d["title"], d["text"], tuple(d["tables"])) for d in schema.DEFINITION_DOCS]
    return docs


class Index:
    def __init__(self, docs: list[Doc] | None = None, k1: float = 1.5, b: float = 0.75):
        self.docs = docs or documents()
        self.toks = [tokens(d.id.split(":", 1)[1].replace("_", " ") + " " + d.text) for d in self.docs]
        self.avg = sum(map(len, self.toks)) / len(self.toks)
        df = Counter(t for toks in self.toks for t in set(toks))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, question: str) -> list[float]:
        q = tokens(question)
        out = []
        for toks in self.toks:
            tf, length, s = Counter(toks), len(toks), 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
            out.append(s)
        return out

    def search(self, question: str) -> list[tuple[Doc, float]]:
        """Top definitions (plus the ALWAYS rules), the tables they use, and the top tables by score."""
        scored = sorted(zip(self.docs, self.scores(question), strict=True), key=lambda p: -p[1])
        defs = [(d, s) for d, s in scored if d.id.startswith("def:") and s > 0][:K_DEFINITIONS]
        always = [(d, 0.0) for d in self.docs if d.id in ALWAYS and all(x.id != d.id for x, _ in defs)]
        tables = {t for d, _ in defs for t in d.tables}
        picked = defs + always
        by_table = [(d, s) for d, s in scored if d.id.startswith("table:")]
        linked = [(d, s) for d, s in by_table if d.tables[0] in tables]
        top = [(d, s) for d, s in by_table if s > 0 and d.tables[0] not in tables][:K_TABLES]
        if not linked and not top:  # nothing matched: give the model the core table rather than nothing
            top = [p for p in by_table if p[0].id == "table:bookings"]
        chosen = {d.tables[0] for d, _ in linked + top}
        partners = {t for d, _ in top for t in d.tables[1:]} - chosen  # e.g. feedback -> bookings for the property
        joined = [(d, s) for d, s in by_table if d.tables[0] in partners]
        return picked + linked + top + joined


_INDEX: Index | None = None


def search(question: str) -> list[tuple[Doc, float]]:
    global _INDEX
    _INDEX = _INDEX or Index()
    return _INDEX.search(question)


def prompt_text(hits: list[tuple[Doc, float]]) -> str:
    tables = [d for d, _ in hits if d.id.startswith("table:")]
    defs = [d for d, _ in hits if d.id.startswith("def:")]
    lines = [
        "SQLite database of a simulated hotel group (synthetic data). All tables: " + ", ".join(schema.TABLES) + ".",
        "Retrieved table docs:",
    ]
    lines += [f"- [{d.id}] {d.text}" for d in tables]
    lines += ["", "Retrieved definitions (use exactly these):"]
    lines += [f"- [{d.id}] {d.text}" for d in defs]
    return "\n".join(lines)
