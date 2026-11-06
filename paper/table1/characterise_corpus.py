"""
Table 1: corpus characterisation for the monograph extraction paper.

Describes the 1,435-PDF corpus as the pipeline sees it. Text is read with
PyPDF2, the same library pdf_utils.py uses, so "no text layer" means "yields no
text to this pipeline".

Each document is written to per_document.csv as soon as it is analysed, and a
rerun skips documents already in that file, so an interrupted run loses nothing.
table1_summary.json is rebuilt from the CSV at the end of every run.
"""

import csv
import json
import os
import re
import statistics
import sys
import warnings
from collections import Counter

import PyPDF2

warnings.filterwarnings("ignore")

CORPUS = r"d:\Western University\Project\Received Monographs\Product monograph"
OUTDIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(OUTDIR, "per_document.csv")
JSON_PATH = os.path.join(OUTDIR, "table1_summary.json")

FRONT_PAGES = 12          # pages read for the TOC, Part markers and dates
MIN_CHARS_PER_PAGE = 50   # below this average a document yields no usable text
DOC_TIMEOUT = 60          # seconds allowed per document before it is skipped

# Headings the pipeline looks for, with the spellings it tries.
SECTIONS = {
    "indications": ["INDICATIONS AND CLINICAL USE", "INDICATIONS"],
    "contraindications": ["CONTRAINDICATIONS"],
    "adverse": ["ADVERSE REACTIONS", "ADVERSE EVENTS"],
    "interactions": ["DRUG INTERACTIONS"],
}

FIELDS = [
    "key", "class", "generic", "filename", "error", "pages", "has_bookmarks",
    "chars_per_sampled_page", "has_text_layer", "has_toc_heading", "toc_leader_lines",
    "has_toc", "part_i", "part_ii", "part_iii", "consumer_information",
    "patient_medication_information", "numbered_sections", "french", "revision_year",
] + [f"{s}_{k}" for s in SECTIONS for k in ("plain", "spaced", "spellings")]


def spaced(text):
    """Regex for `text` that tolerates whitespace between any two characters."""
    return r"\s+".join(r"\s*".join(re.escape(c) for c in word) for word in text.split())


TOC_HEADING_RE = re.compile(spaced("TABLE OF CONTENTS") + "|" + spaced("TABLE DES MATI"), re.I)
LEADER_LINE_RE = re.compile(r"(?:\.\s?){5,}\s*\d{1,3}\s*$", re.M)
NUMBERED_RE = re.compile(r"^\s*1\.?\s+" + spaced("INDICATIONS"), re.M)
YEAR_RE = re.compile(
    r"(?:date\s+of\s+(?:revision|preparation|initial\s+a\w+)|revised|last\s+revised)"
    r"[^\n]{0,60}?\b(19[89]\d|20[0-3]\d)\b", re.I)
FRENCH_RE = re.compile(r"MONOGRAPHIE\s+DE\s+PRODUIT|RENSEIGNEMENTS\s+POUR|CONTRE-INDICATIONS", re.I)


def page_text(reader, i):
    try:
        return reader.pages[i].extract_text() or ""
    except Exception:
        return ""


def analyse(path, rel):
    parts = rel.replace("\\", "/").split("/")
    row = {f: "" for f in FIELDS}
    row.update(key=rel.replace("\\", "/"), filename=parts[-1],
               **{"class": parts[0] if len(parts) > 2 else "",
                  "generic": parts[1] if len(parts) > 2 else ""})
    try:
        with open(path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            n = len(reader.pages)
            row["pages"] = n
            try:
                row["has_bookmarks"] = int(bool(reader.outline))
            except Exception:
                row["has_bookmarks"] = 0

            sample = sorted({0, n // 2, max(n - 1, 0)})
            chars = sum(len(page_text(reader, i)) for i in sample)
            row["chars_per_sampled_page"] = round(chars / len(sample), 1)
            row["has_text_layer"] = int(row["chars_per_sampled_page"] >= MIN_CHARS_PER_PAGE)

            front = "\n".join(page_text(reader, i) for i in range(min(FRONT_PAGES, n)))
            flat = re.sub(r"\s+", " ", front)

            row["has_toc_heading"] = int(bool(TOC_HEADING_RE.search(front)))
            row["toc_leader_lines"] = len(LEADER_LINE_RE.findall(front))
            row["has_toc"] = int(row["has_toc_heading"] or row["toc_leader_lines"] >= 5)

            row["part_i"] = int(bool(re.search(r"PART\s*I\b", flat, re.I)))
            row["part_ii"] = int(bool(re.search(r"PART\s*II\b", flat, re.I)))
            row["part_iii"] = int(bool(re.search(r"PART\s*III\b", flat, re.I)))
            row["consumer_information"] = int(bool(re.search(spaced("CONSUMER INFORMATION"), front, re.I)))
            row["patient_medication_information"] = int(
                bool(re.search(spaced("PATIENT MEDICATION INFORMATION"), front, re.I)))
            row["numbered_sections"] = int(bool(NUMBERED_RE.search(front)))
            row["french"] = int(bool(FRENCH_RE.search(flat)))

            years = [int(y) for y in YEAR_RE.findall(flat)]
            row["revision_year"] = max(years) if years else ""

            for slug, variations in SECTIONS.items():
                plain = any(re.search(re.escape(v), front, re.I) for v in variations)
                loose = any(re.search(spaced(v), front, re.I) for v in variations)
                seen = set()
                for v in variations:
                    for m in re.finditer(spaced(v), front, re.I):
                        seen.add(m.group(0).replace("\n", "\\n"))
                row[f"{slug}_plain"] = int(plain)
                row[f"{slug}_spaced"] = int(loose)
                row[f"{slug}_spellings"] = len(seen)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return row


def quartiles(values):
    s = sorted(values)
    if not s:
        return {}
    q = statistics.quantiles(s, n=4, method="inclusive") if len(s) > 1 else [s[0]] * 3
    return {"min": s[0], "q1": q[0], "median": q[1], "q3": q[2], "max": s[-1]}


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def summarise():
    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ok = [r for r in rows if not r["error"]]
    text = [r for r in ok if r["has_text_layer"] == "1"]

    def count(col, pool=text):
        return sum(1 for r in pool if r[col] == "1")

    def pct(n, pool=text):
        return round(100 * n / max(len(pool), 1), 1)

    summary = {
        "documents": len(rows),
        "unreadable": len(rows) - len(ok),
        "therapeutic_classes": len({r["class"] for r in ok}),
        "generic_drugs": len({(r["class"], r["generic"]) for r in ok}),
        "pages": quartiles([to_int(r["pages"]) for r in ok if to_int(r["pages"])]),
        "text_layer": {"with_text": len(text), "without_text": len(ok) - len(text),
                       "pct_without_text": pct(len(ok) - len(text), ok)},
        "bookmarks": {"n": count("has_bookmarks", ok), "pct": pct(count("has_bookmarks", ok), ok)},
        "table_of_contents": {
            "with_toc": count("has_toc"), "without_toc": len(text) - count("has_toc"),
            "pct_without_toc": pct(len(text) - count("has_toc")),
            "with_toc_heading": count("has_toc_heading"),
        },
        "parts": {p: count(p) for p in ("part_i", "part_ii", "part_iii")},
        "template_markers": {
            "consumer_information": count("consumer_information"),
            "patient_medication_information": count("patient_medication_information"),
            "numbered_sections": count("numbered_sections"),
        },
        "french": count("french"),
        "revision_year": quartiles([to_int(r["revision_year"]) for r in text if to_int(r["revision_year"])]),
        "revision_year_found_in": sum(1 for r in text if to_int(r["revision_year"])),
        "headings": {},
        "per_class": dict(sorted(Counter(r["class"] for r in ok).items())),
    }
    for slug in SECTIONS:
        plain, loose = count(f"{slug}_plain"), count(f"{slug}_spaced")
        summary["headings"][slug] = {
            "found_as_plain_text": plain,
            "found_only_with_spacing_tolerance": loose - plain,
            "not_found_in_front_pages": len(text) - loose,
        }
    with open(JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main():
    files = []
    for dirpath, _dirs, names in os.walk(CORPUS):
        for nm in names:
            if nm.lower().endswith(".pdf"):
                full = os.path.join(dirpath, nm)
                files.append((full, os.path.relpath(full, CORPUS)))
    files.sort(key=lambda t: t[1])

    done = set()
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as fh:
            done = {r["key"] for r in csv.DictReader(fh)}
    todo = [(f, r) for f, r in files if r.replace("\\", "/") not in done]
    print(f"{len(files)} PDFs, {len(done)} already done, {len(todo)} to do", flush=True)

    # PyPDF2 can loop forever on a malformed page, so each document is analysed
    # in a worker process that is killed and replaced if it exceeds the limit.
    import multiprocessing as mp

    new_file = not os.path.exists(CSV_PATH)
    pool = mp.Pool(1)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for i, (full, rel) in enumerate(todo, 1):
            try:
                row = pool.apply_async(analyse, (full, rel)).get(timeout=DOC_TIMEOUT)
            except mp.TimeoutError:
                pool.terminate()
                pool = mp.Pool(1)
                parts = rel.replace("\\", "/").split("/")
                row = {f: "" for f in FIELDS}
                row.update(key=rel.replace("\\", "/"), filename=parts[-1],
                           error=f"timeout after {DOC_TIMEOUT}s",
                           **{"class": parts[0], "generic": parts[1] if len(parts) > 2 else ""})
                print(f"  timeout: {rel}", flush=True)
            writer.writerow(row)
            fh.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    pool.terminate()
    summarise()


if __name__ == "__main__":
    sys.exit(main())
