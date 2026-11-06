"""Section location for the third version of the pipeline.

1. PDF bookmarks: most monographs have a bookmark for every main section.
   A section runs from its bookmark to the next main-section bookmark, and
   the text is cut at the two headings on those pages.
2. Without bookmarks: search the text for the section title at the start of
   a line, skip matches that look like the table of contents, and end the
   section at the next main heading.

There is no fixed character window: the whole section is returned, and long
sections are split into pieces later (see pipeline_v3.chunks).
"""
import re

import PyPDF2

# Titles of the main sections (after an optional number such as "7" or "7.").
MAJOR = [
    r"INDICATIONS", r"CONTRA-?\s*INDICATIONS", r"SERIOUS\s+WARNINGS", r"WARNINGS", r"PRECAUTIONS",
    r"DOSAGE\s+AND\s+ADMINISTRATION", r"DOSAGE\s+&\s+ADMINISTRATION", r"OVERDOS", r"SYMPTOMS\s+AND\s+TREATMENT\s+OF\s+OVERDOS",
    r"ADVERSE\s+(REACTIONS|EVENTS|DRUG\s+REACTIONS)", r"DRUG\s+INTERACTIONS", r"INTERACTIONS",
    r"(ACTION\s+AND\s+)?CLINICAL\s+PHARMACOLOGY", r"ACTION\b", r"STORAGE", r"SPECIAL\s+HANDLING",
    r"DOSAGE\s+FORMS", r"AVAILABILITY", r"PART\s+(I|II|III|1|2|3)\b", r"PHARMACEUTICAL\s+INFORMATION",
    r"CLINICAL\s+TRIALS", r"MICROBIOLOGY", r"IN\s+VITRO", r"(NON-?\s*CLINICAL\s+)?TOXICOLOGY",
    r"DETAILED\s+PHARMACOLOGY", r"PHARMACOLOGY", r"REFERENCES", r"BIBLIOGRAPHY", r"SUPPORTING\s+PRODUCT",
    r"PATIENT\s+MEDICATION", r"CONSUMER\s+INFORMATION", r"SUMMARY\s+PRODUCT", r"THERAPEUTIC\s+CLASSIFICATION",
    r"RECENT\s+MAJOR", r"TABLE\s+OF\s+CONTENTS",
]
MAJOR_RE = re.compile(r"^\W*(\d{1,2}(\.\d)?\.?\s*)?(" + "|".join(MAJOR) + r")", re.I)
NUM_PREFIX = re.compile(r"^\W*\d{1,2}(\.\d{1,2})*\.?\s*")
SUBSECTION = re.compile(r"^\W*\d{1,2}\.\d")

# Field -> bookmark title pattern (matched after removing the number).
FIELD_TITLE = {
    "indications": r"^INDICATIONS",
    "contraindications": r"^CONTRA-?\s*INDICATIONS",
    "box": r"^SERIOUS\s+WARNINGS",
    "warnings": r"^(WARNINGS|PRECAUTIONS)",
    "adverse": r"^ADVERSE\s+(REACTIONS|EVENTS|DRUG\s+REACTIONS)",
    "interactions": r"^(DRUG\s+)?INTERACTIONS",
    "dosage": r"^DOSAGE\s+(AND|&)\s+ADMINISTRATION",
}
# Text-search patterns (start of a line, optional number).
FIELD_TEXT = {
    "indications": r"INDICATIONS(\s+AND\s+CLINICAL\s+USE)?",
    "contraindications": r"CONTRA-?\s*INDICATIONS",
    "box": r"SERIOUS\s+WARNINGS\s+AND\s+PRECAUTIONS(\s+BOX)?",
    "warnings": r"WARNINGS\s+AND\s+PRECAUTIONS|WARNINGS|PRECAUTIONS",
    "adverse": r"ADVERSE\s+(REACTIONS|EVENTS)",
    "interactions": r"DRUG\s+INTERACTIONS",
    "dosage": r"DOSAGE\s+AND\s+ADMINISTRATION",
}
END_OF_PART_I = re.compile(r"^\W*(PART\s+(II|III|2|3)\b|PATIENT\s+MEDICATION|CONSUMER\s+INFORMATION)", re.I)


def bookmarks(reader):
    out = []

    def walk(items, depth):
        for x in items:
            if isinstance(x, list):
                walk(x, depth + 1)
                continue
            try:
                out.append((depth, " ".join(str(x.title).split()), reader.get_destination_page_number(x) + 1))
            except Exception:
                pass
    try:
        walk(reader.outline, 0)
    except Exception:
        return []
    return out


def _title_regex(title):
    """Heading pattern built from a bookmark title, tolerant of extra spaces and broken words."""
    words = re.findall(r"[A-Za-z]+", NUM_PREFIX.sub("", title))[:4]
    if not words:
        return None
    parts = [r"\s*".join(map(re.escape, w)) for w in words]  # PyPDF2 sometimes splits letters
    return re.compile(r"\W+".join(parts), re.I)


def _at_line_start(text, pos):
    """True if only a section number (or nothing) comes before pos on its line."""
    line = text[text.rfind("\n", 0, pos) + 1:pos]
    return re.fullmatch(r"[\s\d.]*", line) is not None


def _cut(pages, start_page, start_title, end_page, end_title):
    """Text from the heading of start_title to the heading of end_title.

    A bookmark can point to the page after its heading, so the page before
    start_page is also searched. Headings must start a line and must not be
    inside a cross-reference such as "(see 4 DOSAGE AND ADMINISTRATION)".
    """
    by_num = {p["page_num"]: p["text"] for p in pages}
    nums = [n for n in sorted(by_num) if start_page - 1 <= n <= end_page]
    if not nums:
        return ""
    text, offs = "", {}
    for n in nums:
        offs[n] = len(text)
        text += by_num[n] + "\n"
    start_off = offs.get(start_page, offs[nums[0]])
    prev_off = offs.get(start_page - 1)

    def heads(rx, lo, hi):
        return [m.start() for m in rx.finditer(text, lo, hi)
                if _at_line_start(text, m.start()) and not _is_reference(text, m.start())]

    s = start_off
    rx = _title_regex(start_title)
    if rx:
        on_page = heads(rx, start_off, len(text) if start_page == nums[-1] else offs.get(start_page + 1, len(text)))
        before = heads(rx, prev_off, start_off) if prev_off is not None else []
        if on_page:
            s = on_page[0]
        elif before:
            s = before[-1]
    e = len(text)
    if end_title is not None:
        rx_end = _title_regex(end_title)
        if rx_end:
            found = heads(rx_end, s + 20, len(text))
            if found:
                e = found[0]
    return text[s:e].strip()


def section_by_bookmarks(reader, pages, field):
    bms = bookmarks(reader)
    if not bms:
        return None
    # Keep Part I only (stop at Part II / patient information).
    part1 = []
    for b in bms:
        if part1 and END_OF_PART_I.match(b[1]):
            part1.append(b)  # keep as an end marker
            break
        part1.append(b)
    # Main sections only: subsections such as "9.2 Drug Interactions Overview"
    # (a decimal number) are skipped, and the section ends at the next main
    # bookmark that is not deeper than its own bookmark.
    majors = [b for b in part1 if MAJOR_RE.match(b[1]) and not SUBSECTION.match(b[1])]
    pat = re.compile(FIELD_TITLE[field], re.I)
    for i, (depth, title, page) in enumerate(majors):
        bare = NUM_PREFIX.sub("", title)
        if not pat.match(bare):
            continue
        if field == "indications" and re.match(r"CONTRA", bare, re.I):
            continue
        if field == "warnings" and re.match(r"SERIOUS", bare, re.I):
            continue
        j = i + 1
        while j < len(majors) and majors[j][0] > depth:
            j += 1
        # Old monographs have WARNINGS and PRECAUTIONS as two sections: keep both.
        if field == "warnings":
            while j < len(majors) and re.match(r"^(WARNINGS|PRECAUTIONS)", NUM_PREFIX.sub("", majors[j][1]), re.I):
                j += 1
        if j < len(majors):
            end_title, end_page = majors[j][1], majors[j][2]
        else:
            end_title, end_page = None, max(p["page_num"] for p in pages)
        text = _cut(pages, page, title, max(end_page, page), end_title)
        if text:
            return text
    return None


# ---------- fallback: text search ----------

def _toc_like(window):
    return bool(re.search(r"\.{4,}|(\.\s){4,}", window)) or len(re.findall(r"[A-Za-z]{4,}", window)) < 15


def _is_reference(full, pos):
    before = full[max(0, pos - 120):pos]
    if re.search(r"(see|refer\s+to|described\s+in|outlined\s+in|under)\s*(section\s*)?[\d.\s]*$", before, re.I):
        return True
    o, c = max(before.rfind("("), before.rfind("[")), max(before.rfind(")"), before.rfind("]"))
    return o > c


def section_by_text(full, field):
    pat = re.compile(r"(?m)^[ \t]*(\d{1,2}(\.\d)?\.?[ \t]*)?(" + FIELD_TEXT[field] + r")\b", re.I if field == "box" else 0)
    for m in pat.finditer(full):
        st = m.start(3)
        if _is_reference(full, st) or _toc_like(full[st:st + 400]):
            continue
        if field == "indications" and full[max(0, st - 6):st].upper().endswith("CONTRA"):
            continue
        # End at the next main heading at the start of a line.
        end = len(full)
        for h in re.finditer(r"(?m)^[ \t]*(\d{1,2}(\.\d)?\.?[ \t]*)?(" + "|".join(MAJOR) + r")\b", full[st + 30:]):
            title = h.group(3).upper()
            if field == "warnings" and re.match(r"(WARNINGS|PRECAUTIONS)", title):
                continue
            if field == "box" and re.match(r"(SERIOUS|WARNINGS|PRECAUTIONS)", title):
                continue
            end = st + 30 + h.start()
            break
        return full[st:end].strip()
    return None


def find_section(pdf_path, pages, field):
    """Return (text, method) for a field, or (None, None)."""
    try:
        reader = PyPDF2.PdfReader(pdf_path)
        t = section_by_bookmarks(reader, pages, field)
        if t:
            return t, "bookmarks"
    except Exception:
        pass
    full = "\n".join(p["text"] for p in pages)
    t = section_by_text(full, field)
    if t:
        return t, "text search"
    return None, None


def subsection_by_bookmarks(pdf_path, pages, title_pattern, stop_after_part_i=True):
    """A subsection (any depth) such as 'Pregnant Women', up to the next bookmark."""
    try:
        bms = bookmarks(PyPDF2.PdfReader(pdf_path))
    except Exception:
        return None
    pat = re.compile(title_pattern, re.I)
    for i, (d, title, page) in enumerate(bms):
        if stop_after_part_i and END_OF_PART_I.match(title) and i > 0:
            break
        if pat.search(title):
            nxt = bms[i + 1] if i + 1 < len(bms) else None
            end_title, end_page = (nxt[1], nxt[2]) if nxt else (None, page)
            return _cut(pages, page, title, max(end_page, page), end_title) or None
    return None


def keyword_passages(text, keywords, width=500, limit=6000):
    """Short passages around each keyword (merged where they overlap)."""
    if not text:
        return ""
    spans = []
    for m in re.finditer(keywords, text, re.I):
        a, b = max(0, m.start() - width), min(len(text), m.end() + width)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    out = "\n...\n".join(text[a:b] for a, b in spans)
    return out[:limit]
