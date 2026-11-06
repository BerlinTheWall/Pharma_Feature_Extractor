"""Run the third version of the pipeline on Set A (development) or Set B (held-out).

Same model server, client and temperature as the original runs
(code_aug27/pharma_extractor_package: config.py and api_client.py).
Set B outputs go to ../heldout/runs/sealed_outputs and must not be opened
until the physician's answer sheet is reviewed and frozen.

Usage (Git Bash):
    PHARMA_EXTRACTOR_MODEL=qwen2.5-7b-ctx32k python run_v3.py --set A --out qwen_v3_setA.xlsx
"""
import argparse
import json
import os
import sys
import time

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "heldout", "runs")
sys.path.insert(0, os.path.join(RUNS, "code_aug27"))
sys.path.insert(0, RUNS)
sys.path.insert(0, HERE)

import pharma_extractor_package as pkg  # noqa: E402
assert os.path.abspath(pkg.__file__).startswith(os.path.abspath(os.path.join(RUNS, "code_aug27")))
from pharma_extractor_package.config import DEFAULT_MODEL, API_BASE_URL  # noqa: E402
from pharma_extractor_package.api_client import call_ai_api  # noqa: E402
import run_setB  # noqa: E402  (same lists of monographs and PDF paths)
import pipeline_v3 as V3  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["A", "B"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.set == "A":
        items, out_dir = run_setB.set_a_items(), os.path.join(HERE, "setA_outputs")
    else:
        import csv
        with open(run_setB.SET_CSV, encoding="utf-8") as f:
            rows_b = list(csv.DictReader(f))
        pdf_files = {fn.split(" - ", 1)[1]: fn for fn in os.listdir(run_setB.PDF_DIR)}
        items = [{"id": r["filename"].lower().replace(".pdf", "").strip(), "generic": r["generic"], "class": r["class"],
                  "path": os.path.join(run_setB.PDF_DIR, pdf_files[r["filename"]])} for r in rows_b]
        out_dir = run_setB.OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.out)
    print(f"Model: {DEFAULT_MODEL} | Endpoint: {API_BASE_URL} | Version: v3 | Set {args.set}")

    rows, done = [], set()
    if os.path.exists(out_path):
        old = pd.read_excel(out_path)
        rows, done = old.to_dict("records"), set(old["ID"].astype(str))
        print(f"Resuming: {len(done)} already done")
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    n_calls = [0]
    items = items if args.limit is None else items[:args.limit]
    for i, it in enumerate(items):
        if it["id"] in done:
            continue
        print(f"\n[{i + 1}/{len(items)}] {it['generic']} ({os.path.basename(it['path'])})")
        t0 = time.time()

        def call(prompt, system):
            n_calls[0] += 1
            return call_ai_api(prompt, system, it["id"], temperature=0.1)

        row = {"ID": it["id"], "Drug Name": it["generic"], "Drug Class": it["class"]}
        row.update(V3.extract_all(it["path"], it["generic"], call))
        row["_seconds"] = round(time.time() - t0, 1)
        for k, v in row.items():
            if isinstance(v, str):
                row[k] = ILLEGAL_CHARACTERS_RE.sub("", v)
        print(f"  done in {row['_seconds']}s, {n_calls[0]} calls so far")
        rows.append(row)
        pd.DataFrame(rows).to_excel(out_path, index=False)

    info = {"model": DEFAULT_MODEL, "endpoint": API_BASE_URL, "version": "v3", "set": args.set,
            "started": started, "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": len(rows), "calls": n_calls[0]}
    with open(out_path.replace(".xlsx", "_run_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"\nSaved {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
