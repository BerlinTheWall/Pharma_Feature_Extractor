"""
Draw the held-out test set for the pipeline comparison.

Same scheme as the development set: one monograph per therapeutic class plus a
second from the largest class, chosen at random with a fixed seed.

Excluded before drawing:
  - the 20 development monographs,
  - other strengths of a development product (same generic folder and same
    product name once the strength is removed), since those monographs are
    usually the same document,
  - files with no text layer or that could not be read (Table 1).

Writes heldout_test_set.csv, an empty annotation template with the gold-standard
columns, and copies the 20 PDFs into ./pdfs for annotation.
"""

import csv
import os
import random
import re
import shutil

import pandas as pd

SEED = 20261005
CORPUS = r"d:\Western University\Project\Received Monographs\Product monograph"
GOLD = r"d:\Western University\Project\Received Monographs\Final extractions\ground_truth_monograph_extractions.xlsx"
HERE = os.path.dirname(os.path.abspath(__file__))
TABLE1 = os.path.join(HERE, "..", "table1", "per_document.csv")


# Development IDs whose spelling in the gold standard differs from the file name.
# File names are taken from gold_sample_candidates.csv, which recorded the
# monograph chosen for each drug when the development set was built.
DEV_OVERRIDES = {
    "apotex-500mg": ("Amoxicillin trihydrate", "Apotex-500mg.pdf"),
    "sandoz bisoprolol 5mg": ("Bisoprolol", "SANDOZ BISOPROLOL TABLETS 5mg.pdf"),
    "lupin-cephalexin 125mg-250mg/5ml": ("Cefalexin", "LUPIN-CEPHALEXIN 125mg 5ml.pdf"),
    "lasix-10mg/ml": ("Furosemide", "LASIX ORAL SOLUTION 10mg ml.pdf"),
    "septra injection 80mg-16mg/ml": (None, "SEPTRA INJECTION 16mg per ml.pdf"),
    "jamp-fosfomycin 3g": ("Fosfomycin", "JAMP-FOSFOMYCIN 3g sachet.pdf"),
    "azithromycin for injection 500mg": ("Azithromycin", "AZITHROMYCIN FOR INJECTION, USP 500mg per vial.pdf"),
}


def stem(filename):
    return re.sub(r"\.pdf$", "", filename, flags=re.I).lower().strip()


def norm(text):
    return re.sub(r"[^a-z0-9]", "", stem(text))


def product(filename):
    """Product name with the strength removed, e.g. 'APO-ENALAPRIL 5mg.pdf' -> 'apoenalapril'."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[\s\-_]+\d.*$", "", stem(filename)))


def same_product(doc, dev_docs):
    p = product(doc["filename"])
    return any(doc["generic"] == d["generic"]
               and (p.startswith(product(d["filename"])) or product(d["filename"]).startswith(p))
               for d in dev_docs)


def main():
    with open(TABLE1, newline="", encoding="utf-8") as fh:
        docs = [r for r in csv.DictReader(fh)]

    gold = pd.read_excel(GOLD)
    dev_docs = []
    for gold_id in (str(i).lower().strip() for i in gold["ID"]):
        if gold_id in DEV_OVERRIDES:
            generic, name = DEV_OVERRIDES[gold_id]
            hits = [d for d in docs if d["filename"] == name and generic in (None, d["generic"])]
        else:
            hits = [d for d in docs if norm(d["filename"]) == norm(gold_id)]
        if len(hits) != 1:
            raise SystemExit(f"development monograph not resolved to one file: {gold_id!r} -> {len(hits)} files")
        dev_docs.append(hits[0])
    dev_keys = {d["key"] for d in dev_docs}
    print(f"development monographs matched in corpus: {len(dev_keys)} of {len(gold)}")

    eligible, dropped = [], {"development": 0, "same product as development": 0, "no text or unreadable": 0}
    for d in docs:
        if d["key"] in dev_keys:
            dropped["development"] += 1
        elif same_product(d, dev_docs):
            dropped["same product as development"] += 1
        elif d["error"] or d["has_text_layer"] != "1":
            dropped["no text or unreadable"] += 1
        else:
            eligible.append(d)
    print(f"eligible: {len(eligible)} of {len(docs)}; excluded: {dropped}")

    by_class = {}
    for d in eligible:
        by_class.setdefault(d["class"], []).append(d)
    for members in by_class.values():
        members.sort(key=lambda d: d["key"])

    rng = random.Random(SEED)
    chosen = [rng.choice(by_class[c]) for c in sorted(by_class)]
    largest = max(sorted(by_class), key=lambda c: len(by_class[c]))
    first = next(d for d in chosen if d["class"] == largest)
    rest = [d for d in by_class[largest] if not same_product(d, [first])]
    chosen.append(rng.choice(rest))

    shutil.rmtree(os.path.join(HERE, "pdfs"), ignore_errors=True)
    os.makedirs(os.path.join(HERE, "pdfs"))
    with open(os.path.join(HERE, "heldout_test_set.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["n", "class", "generic", "filename", "pages", "has_toc", "seed"])
        for n, d in enumerate(chosen, 1):
            w.writerow([n, d["class"], d["generic"], d["filename"], d["pages"], d["has_toc"], SEED])
            shutil.copy2(os.path.join(CORPUS, d["key"].replace("/", os.sep)),
                         os.path.join(HERE, "pdfs", f"{n:02d} - {d['filename']}"))

    template = pd.DataFrame(columns=[c for c in gold.columns
                                     if c not in ("severity_score_percent", "severity_category")])
    template["ID"] = [stem(d["filename"]) for d in chosen]
    template.to_excel(os.path.join(HERE, "heldout_annotation_template.xlsx"), index=False)

    print(f"\nseed {SEED}; largest class: {largest}")
    for n, d in enumerate(chosen, 1):
        print(f"{n:>2}  {d['class'][:34]:<34}  {d['generic'][:24]:<24}  {d['filename']}  ({d['pages']} p)")


if __name__ == "__main__":
    main()
