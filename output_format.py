"""Enforcement of the comma-separated keyword contract.

Indications, contraindications, adverse events and drug interactions are list
fields: the value must be keywords or short key phrases separated by commas and
nothing else. A 7B model asked for that will still occasionally return a
summary, a numbered list, or a helpful preamble -- and once that prose is in
the spreadsheet it is indistinguishable from data for every downstream
consumer.

Prompting alone does not fix this; the model has to be checked. This module is
the check. It normalizes what can be salvaged (surrounding quotes, bullets,
numbering, a stray "and") and rejects what cannot, so the caller can retry or
record an explicit failure instead of storing prose.
"""

import re
from typing import List, Optional, Tuple

# Values that are legitimate non-list answers and must pass through untouched.
SENTINELS = {
    "NO_ADVERSE_EVENTS_FOUND",
    "NO_TEXT_FOUND",
    "SECTION_NOT_FOUND",
    "EXTRACTION_FAILED",
    "CONTENT_EXTRACTION_FAILED",
    "TEXT_EXTRACTION_ERROR",
    "SUMMARY_GENERATION_FAILED",
    "******",
    "********",
}

# Phrases that only ever appear when the model has started talking to us
# instead of extracting. Any of these means the answer is prose.
PROSE_MARKERS = (
    "the text you provided",
    "the text provided",
    "it appears you",
    "you've provided",
    "you have provided",
    "here's a summary",
    "here is a summary",
    "here's the",
    "here is the",
    "in summary",
    "to summarize",
    "i recommend",
    "please note",
    "please consult",
    "consulting the original",
    "healthcare professional",
    "for more detailed information",
    "based on the text",
    "the following is",
    "this text describes",
    "is a summary of",
)

# Leading label the model sometimes prepends, e.g. "Adverse events: dizziness, ..."
_LEADING_LABEL = re.compile(
    r"^\s*(adverse\s+events?|adverse\s+reactions?|indications?(\s+of\s+use)?|"
    r"contraindications?|drug\s+interactions?|drugs?|conditions?|keywords?|"
    r"output|answer|result)\s*[:\-]\s*",
    re.IGNORECASE,
)

# Bullet, numbering and markdown noise at the start of an item.
_ITEM_PREFIX = re.compile(r"^\s*(?:[-*•·]|\(?\d+[.)])\s*")

# A sentence boundary: '.', '!' or '?' followed by whitespace and a capital.
_SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")

# An item long enough to be a clause rather than a key phrase.
MAX_WORDS_PER_ITEM = 12
# Items longer than this are dropped outright.
HARD_MAX_WORDS_PER_ITEM = 20
# If dropping over-long items removes more than this share, reject the answer.
MAX_DROPPED_FRACTION = 0.5


def _strip_wrapping_quotes(text: str) -> str:
    """Remove one layer of surrounding quotes the model sometimes adds."""
    text = text.strip()
    for opening, closing in (('"', '"'), ("'", "'"), ("“", "”")):
        if len(text) >= 2 and text.startswith(opening) and text.endswith(closing):
            return text[1:-1].strip()
    return text


def _strip_code_fence(text: str) -> str:
    """Remove a markdown code fence wrapper if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        return "\n".join(lines).strip()
    return text


def looks_like_prose(text: str) -> Optional[str]:
    """
    Return a reason string if `text` is prose rather than a list, else None.
    """
    lowered = text.lower()

    for marker in PROSE_MARKERS:
        if marker in lowered:
            return f"contains conversational phrase {marker!r}"

    if "\n\n" in text.strip():
        return "contains multiple paragraphs"

    # A bulleted or numbered list of short keywords is just the right data in
    # the wrong shape -- normalization salvages it. The same structure holding
    # long clauses is a written summary, and is rejected.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1:
        bulleted = [ln for ln in lines if _ITEM_PREFIX.match(ln)]
        if len(bulleted) >= 2:
            longest = max(len(_ITEM_PREFIX.sub("", ln).split()) for ln in bulleted)
            if longest > MAX_WORDS_PER_ITEM:
                return "bulleted list of long clauses"

    if _SENTENCE_BREAK.search(text):
        return "contains sentence breaks"

    # A single long run with no commas is a sentence, not a list.
    if "," not in text and len(text.split()) > MAX_WORDS_PER_ITEM:
        return "single long phrase with no commas"

    return None


def _clean_item(item: str) -> str:
    """Normalize one list entry."""
    item = _ITEM_PREFIX.sub("", item)
    item = item.strip().strip('"“”').strip()
    item = re.sub(r"^and\s+", "", item, flags=re.IGNORECASE)
    item = re.sub(r"\s+", " ", item)
    # Drop a trailing full stop, but keep abbreviations like "b.i.d."
    if item.endswith(".") and not re.search(r"\b\w\.\w\.$", item):
        item = item[:-1].strip()
    return item


def _normalize_for_match(text: str) -> str:
    """Lowercase and strip punctuation, for loose containment tests."""
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def grounded_fraction(items: List[str], source_text: str) -> float:
    """
    Share of `items` that plausibly come from `source_text`.

    Matching is deliberately loose -- a six-character prefix of the item's
    longest word -- so legitimate morphology ("hypertension" extracted from
    "hypertensive patients") still counts as grounded. It is meant to catch
    wholesale invention, not to police wording.
    """
    if not items:
        return 1.0

    haystack = _normalize_for_match(source_text)
    hits = 0
    for item in items:
        normalized = _normalize_for_match(item).strip()
        if not normalized:
            continue
        if normalized in haystack:
            hits += 1
            continue
        words = [w for w in normalized.split() if len(w) >= 5] or normalized.split()
        if words:
            stem = max(words, key=len)[:6]
            if len(stem) >= 4 and stem in haystack:
                hits += 1

    return hits / len(items)


# Below this share of grounded items the answer is treated as invented rather
# than extracted. Set low enough to tolerate paraphrase and abbreviation.
MIN_GROUNDED_FRACTION = 0.5


def normalize_keyword_list(
    raw: str,
    source_text: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Coerce a model answer into the comma-separated keyword contract.

    Returns:
        (value, reason). On success `value` is the normalized string and
        `reason` is "ok". On failure `value` is None and `reason` explains
        why, so the caller can retry or record the failure.
    """
    if raw is None:
        return None, "empty response"

    text = raw.strip()
    if not text:
        return None, "empty response"

    if text in SENTINELS:
        return text, "ok"

    text = _strip_code_fence(text)
    text = _strip_wrapping_quotes(text)
    text = _LEADING_LABEL.sub("", text)
    text = _strip_wrapping_quotes(text)

    if text in SENTINELS:
        return text, "ok"

    prose_reason = looks_like_prose(text)
    if prose_reason:
        return None, prose_reason

    # Newlines and semicolons are treated as separators so a clean one-per-line
    # answer is salvageable rather than rejected.
    parts = re.split(r"[,\n;]+", text)

    items: List[str] = []
    seen = set()
    dropped = 0
    for part in parts:
        item = _clean_item(part)
        if not item:
            continue
        word_count = len(item.split())
        if word_count > HARD_MAX_WORDS_PER_ITEM:
            dropped += 1
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    if not items:
        return None, "no list items found"

    if dropped and dropped / (dropped + len(items)) > MAX_DROPPED_FRACTION:
        return None, f"{dropped} of {dropped + len(items)} items were over-long"

    # A well-formed list of terms that are not in the document is worse than
    # prose: it looks like clean data. This is what catches the model echoing
    # the prompt's own example instead of reading the monograph.
    if source_text:
        grounded = grounded_fraction(items, source_text)
        if grounded < MIN_GROUNDED_FRACTION:
            return None, (
                f"only {grounded:.0%} of {len(items)} terms appear in the source "
                f"text (likely invented or copied from the prompt)"
            )

    return ", ".join(items), "ok"
