"""Do the PDF bookmarks name the target sections and point to a page?"""
import csv, json, os, re, warnings
from collections import Counter
import PyPDF2
warnings.filterwarnings("ignore")
import logging; logging.disable(logging.CRITICAL)

CORPUS = r"d:\Western University\Project\Received Monographs\Product monograph"
TARGETS = {
    "indications": r"(?<!CONTRA)INDICATIONS",
    "contraindications": r"CONTRAINDICATIONS",
    "warnings": r"WARNINGS\s+AND\s+PRECAUTIONS",
    "adverse": r"ADVERSE\s+(REACTIONS|EVENTS)",
    "interactions": r"DRUG\s+INTERACTIONS",
}

def flatten(outline, depth=0):
    for item in outline:
        if isinstance(item, list):
            yield from flatten(item, depth + 1)
        else:
            yield depth, item

rows = [r for r in csv.DictReader(open("per_document.csv", encoding="utf-8")) if not r["error"]]
out, depth_counts, sizes = [], Counter(), []
examples = []
for r in rows:
    rec = {"key": r["key"], "n_bookmarks": 0}
    try:
        with open(os.path.join(CORPUS, r["key"]), "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            items = list(flatten(reader.outline))
            rec["n_bookmarks"] = len(items)
            for name, rx in TARGETS.items():
                hit = next(((d, it) for d, it in items if re.search(rx, str(it.title), re.I)), None)
                rec[name] = 0
                if hit:
                    try:
                        page = reader.get_destination_page_number(hit[1])
                        rec[name] = 1 if page is not None and page >= 0 else 0
                        rec[name + "_page"] = page + 1
                    except Exception:
                        rec[name] = 0
            if len(examples) < 3 and items:
                examples.append((r["key"], [str(it.title)[:60] for _, it in items[:14]]))
    except Exception as e:
        rec["error"] = str(e)[:80]
    out.append(rec)

n = len(out)
summary = {"documents": n,
           "with_any_bookmark": sum(1 for o in out if o["n_bookmarks"] > 0),
           "bookmarks_per_doc_median": sorted(o["n_bookmarks"] for o in out)[n // 2],
           "few_bookmarks_under_5": sum(1 for o in out if 0 < o["n_bookmarks"] < 5)}
for name in TARGETS:
    k = sum(1 for o in out if o.get(name) == 1)
    summary[name] = {"bookmark_with_page": k, "pct": round(100 * k / n, 1)}
allk = sum(1 for o in out if all(o.get(t) == 1 for t in TARGETS))
four = sum(1 for o in out if all(o.get(t) == 1 for t in ("indications", "contraindications", "adverse", "interactions")))
summary["all_five_sections"] = {"n": allk, "pct": round(100 * allk / n, 1)}
summary["four_list_sections"] = {"n": four, "pct": round(100 * four / n, 1)}
json.dump({"summary": summary, "rows": out}, open("bookmark_check.json", "w"), indent=1)
print(json.dumps(summary, indent=2))
for k, titles in examples:
    print("\n", k); [print("   ", t) for t in titles]
