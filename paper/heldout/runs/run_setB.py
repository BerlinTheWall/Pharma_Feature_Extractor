"""Run the pipeline on the held-out set (Set B, 20 monographs).

Uses the code exactly as it was at git commit 3d08736 (27 Aug 2026), the
version the Methods section describes, copied into ./code_aug27. The v2
section finder comes from "Received Monographs/Final extractions", unchanged
since 20 Aug 2026. v2 changes only the four list fields; serious warnings and
the categorical fields use the original extractors, as in Methods 3.5.

Outputs go to ./sealed_outputs and must not be opened until the physician's
answer sheet for Set B has been reviewed and frozen.

Usage:
    set PHARMA_EXTRACTOR_MODEL=qwen2.5:7b
    python run_setB.py --variant v1 --out qwen_v1_setB.xlsx
"""
import argparse
import csv
import json
import os
import sys
import time

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
AUG_CODE = os.path.join(HERE, "code_aug27")
V2_DIR = r"D:\Western University\Project\Received Monographs\Final extractions"
HELDOUT = os.path.dirname(HERE)
PDF_DIR = os.path.join(HELDOUT, "pdfs")
SET_CSV = os.path.join(HELDOUT, "heldout_test_set.csv")
OUT_DIR = os.path.join(HERE, "sealed_outputs")
SETA_OUT_DIR = os.path.join(HERE, "setA_outputs")
SETA_KEY = os.path.join(V2_DIR, "ground_truth_monograph_extractions_FROZEN_2026-10-05.xlsx")
SETA_CANDIDATES = os.path.join(V2_DIR, "gold_sample_candidates.csv")
DRUG_NAME_ALIASES = {"cephalexin": "cefalexin", "amoxicillin": "amoxicillin trihydrate"}


def word_bag_key(name):
    import re
    words = re.findall(r"[a-z]{4,}", str(name).lower())
    return " ".join(sorted(w for w in words if w != "and"))


def set_a_items():
    """Set A (development 20): same PDF lookup as run_pipeline_on_ground_truth.py."""
    key = pd.read_excel(SETA_KEY, sheet_name="Ground Truth")
    cand = pd.read_csv(SETA_CANDIDATES)
    by_name = {r["drug_name"].strip().lower(): r["full_path"] for _, r in cand.iterrows()}
    by_bag = {word_bag_key(r["drug_name"]): r["full_path"] for _, r in cand.iterrows()}
    items = []
    for _, r in key.iterrows():
        raw = str(r["Drug Name"]).strip()
        path = by_name.get(DRUG_NAME_ALIASES.get(raw.lower(), raw.lower())) or by_bag.get(word_bag_key(raw))
        assert path and os.path.exists(path), f"No PDF for {raw}"
        items.append({"id": str(r["ID"]), "generic": r["Drug Name"], "class": r["Drug Class"], "path": path})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["v1", "v2"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--set", choices=["A", "B"], default="B")
    args = ap.parse_args()

    # Load the August package first, so later imports (including the one
    # inside improved_extractors.py) reuse it instead of the current code.
    sys.path.insert(0, AUG_CODE)
    import pharma_extractor_package as pkg
    assert os.path.abspath(pkg.__file__).startswith(os.path.abspath(AUG_CODE)), pkg.__file__

    from pharma_extractor_package.config import DEFAULT_MODEL, API_BASE_URL
    from pharma_extractor_package.indications_extractor import extract_indications_from_pdf
    from pharma_extractor_package.contraindications_extractor import extract_contraindications_from_pdf
    from pharma_extractor_package.warnings_extractor import extract_warnings_from_pdf
    from pharma_extractor_package.adverse_events_extractor import extract_adverse_events
    from pharma_extractor_package.drug_interactions_extractor import extract_drug_interactions_from_pdf
    from pharma_extractor_package.liver_extractor import extract_liver_dose_adjustment_from_pdf
    from pharma_extractor_package.kidney_extractor import extract_kidney_dose_adjustment_from_pdf
    from pharma_extractor_package.pregnancy_extractor import extract_pregnancy_from_pdf
    from pharma_extractor_package.breastfeeding_extractor import extract_breastfeeding_from_pdf

    if args.variant == "v2":
        sys.path.insert(1, V2_DIR)
        import improved_extractors as v2
        assert os.path.abspath(sys.modules["pharma_extractor_package"].__file__).startswith(os.path.abspath(AUG_CODE))

    print(f"Model: {DEFAULT_MODEL} | Endpoint: {API_BASE_URL} | Variant: {args.variant}")

    if args.set == "A":
        items = set_a_items()
        out_dir = SETA_OUT_DIR
    else:
        with open(SET_CSV, encoding="utf-8") as f:
            rows_b = list(csv.DictReader(f))
        pdf_files = {fn.split(" - ", 1)[1]: fn for fn in os.listdir(PDF_DIR)}
        items = [{"id": r["filename"].lower().replace(".pdf", "").strip(), "generic": r["generic"],
                  "class": r["class"], "path": os.path.join(PDF_DIR, pdf_files[r["filename"]])}
                 for r in rows_b]
        out_dir = OUT_DIR

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.out)
    rows, done = [], set()
    if os.path.exists(out_path):
        old = pd.read_excel(out_path)
        rows, done = old.to_dict("records"), set(old["ID"].astype(str))
        print(f"Resuming: {len(done)} already done")

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    n = len(items) if args.limit is None else min(args.limit, len(items))
    for i, it in enumerate(items[:n]):
        pid = it["id"]
        if pid in done:
            continue
        pdf_path = it["path"]
        drug = it["generic"]
        print(f"\n[{i+1}/{n}] {drug} ({os.path.basename(pdf_path)})")
        t0 = time.time()
        row = {"ID": pid, "Drug Name": drug, "Drug Class": it["class"]}
        if args.variant == "v1":
            row["Indication of Use"] = extract_indications_from_pdf(pdf_path, drug)
            row["Contraindications"] = extract_contraindications_from_pdf(pdf_path, drug)
            row["Adverse Events"] = extract_adverse_events(pdf_path, drug)
            row["Drug Interactions"] = extract_drug_interactions_from_pdf(pdf_path, drug)
        else:
            row["Indication of Use"] = v2.extract_indications_v2(pdf_path, drug)
            row["Contraindications"] = v2.extract_contraindications_v2(pdf_path, drug)
            row["Adverse Events"] = v2.extract_adverse_events_v2(pdf_path, drug)
            row["Drug Interactions"] = v2.extract_drug_interactions_v2(pdf_path, drug)
        row["Serious warning and precautions"] = extract_warnings_from_pdf(pdf_path, drug)
        row["Liver Function Dose Adjustment"] = extract_liver_dose_adjustment_from_pdf(pdf_path, drug)
        row["Kidney Function Dose Adjustment"] = extract_kidney_dose_adjustment_from_pdf(pdf_path, drug)
        row["Pregnancy Recommendation"] = extract_pregnancy_from_pdf(pdf_path, drug).get("Pregnancy Recommendation")
        row["Breastfeeding Recommendation"] = extract_breastfeeding_from_pdf(pdf_path, drug).get("Breastfeeding Recommendation")
        row["_seconds"] = round(time.time() - t0, 1)
        print(f"  done in {row['_seconds']}s")
        # Excel cannot store some invisible control characters that models
        # sometimes output; drop them (nothing visible is lost).
        for k, val in row.items():
            if isinstance(val, str):
                row[k] = ILLEGAL_CHARACTERS_RE.sub("", val)
        rows.append(row)
        pd.DataFrame(rows).to_excel(out_path, index=False)

    info = {"model": DEFAULT_MODEL, "endpoint": API_BASE_URL, "variant": args.variant,
            "set": args.set, "code": "git 3d08736 (2026-08-27)", "started": started,
            "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": len(rows)}
    with open(out_path.replace(".xlsx", "_run_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"\nSaved {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
