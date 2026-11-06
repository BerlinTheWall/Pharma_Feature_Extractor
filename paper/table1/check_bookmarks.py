"""
Can PDF bookmarks locate the sections the pipeline needs?

For each monograph: flatten the bookmark tree, look for a bookmark naming each
target section, resolve it to a page, and confirm the heading really appears on
that page. Writes bookmarks_per_document.csv and prints a summary.
"""

import csv
import multiprocessing as mp
import os
import re
import statistics
import warnings

import PyPDF2

warnings.filterwarnings("ignore")

CORPUS = r"d:\Western University\Project\Received Monographs\Product monograph"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bookmarks_per_document.csv")
DOC_TIMEOUT = 60

TARGETS = {
    "indications": r"(?<!CONTRA)INDICATIONS",
    "contraindications": r"CONTRAINDICATIONS",
    "warnings": r"WARNINGS\s+AND\s+PRECAUTIONS",
    "adverse": r"ADVERSE\s+(REACTIONS|EVENTS)",
    "interactions": r"DRUG\s+INTERACTIONS",
}
FIELDS = ["key", "error", "n_bookmarks"] + [f"{t}_{k}" for t in TARGETS for k in ("bookmark", "page", "heading_on_page")]


def flatten(outline):
    for item in outline:
        if isinstance(item, list):
            yield from flatten(item)
        else:
            yield item


def analyse(path, key):
    row = {f: "" for f in FIELDS}
    row["key"] = key
    try:
        with open(path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            items = list(flatten(reader.outline))
            row["n_bookmarks"] = len(items)
            for name, rx in TARGETS.items():
                hit = next((it for it in items if re.search(rx, str(getattr(it, "title", "")), re.I)), None)
                row[f"{name}_bookmark"] = int(hit is not None)
                if hit is None:
                    continue
                try:
                    page = reader.get_destination_page_number(hit)
                except Exception:
                    page = None
                if page is None or page < 0:
                    continue
                row[f"{name}_page"] = page + 1
                text = reader.pages[page].extract_text() or ""
                row[f"{name}_heading_on_page"] = int(bool(re.search(rx, text, re.I)))
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:150]
    return row


def main():
    files = []
    for d, _dirs, names in os.walk(CORPUS):
        for nm in names:
            if nm.lower().endswith(".pdf"):
                full = os.path.join(d, nm)
                files.append((full, os.path.relpath(full, CORPUS).replace("\\", "/")))
    files.sort(key=lambda t: t[1])

    rows = []
    pool = mp.Pool(1)
    for i, (full, key) in enumerate(files, 1):
        try:
            rows.append(pool.apply_async(analyse, (full, key)).get(timeout=DOC_TIMEOUT))
        except mp.TimeoutError:
            pool.terminate()
            pool = mp.Pool(1)
            row = {f: "" for f in FIELDS}
            row.update(key=key, error="timeout")
            rows.append(row)
        if i % 200 == 0:
            print(f"  {i}/{len(files)}", flush=True)
    pool.terminate()

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if not r["error"]]
    n = len(ok)
    counts = [int(r["n_bookmarks"]) for r in ok]
    print(f"\ndocuments read: {n} (errors: {len(rows) - n})")
    print(f"with at least one bookmark: {sum(1 for c in counts if c)}")
    print(f"bookmarks per document: median {statistics.median(counts)}, "
          f"with 5 or fewer: {sum(1 for c in counts if c <= 5)}")
    print(f"\n{'section':<20}{'has bookmark':>14}{'page resolves':>15}{'heading on page':>17}")
    for name in TARGETS:
        b = sum(1 for r in ok if r[f"{name}_bookmark"] == "1" or r[f"{name}_bookmark"] == 1)
        p = sum(1 for r in ok if r[f"{name}_page"] != "")
        h = sum(1 for r in ok if str(r[f"{name}_heading_on_page"]) == "1")
        print(f"{name:<20}{b:>8} {100*b/n:4.0f}%{p:>9} {100*p/n:4.0f}%{h:>11} {100*h/n:4.0f}%")
    core = ["indications", "contraindications", "adverse", "interactions"]
    allfour = sum(1 for r in ok if all(str(r[f"{c}_heading_on_page"]) == "1" for c in core))
    print(f"\nall four core sections located and verified: {allfour} ({100*allfour/n:.0f}%)")


if __name__ == "__main__":
    main()
