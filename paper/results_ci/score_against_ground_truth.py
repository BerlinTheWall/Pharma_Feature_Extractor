"""Score any pipeline/model output against the hand-built ground truth.

Usage:
    python score_against_ground_truth.py <predictions.xlsx> [--sheet SHEETNAME] [--out prefix] [--semantic]

Compares the 20-monograph ground truth (ground_truth_monograph_extractions.xlsx,
expected in the same folder as this script by default) against a predictions
file with the same ID/column schema, and reports per-field accuracy /
precision / recall / F1 depending on field type.

Exact-match scoring (default) is pure pandas -- any Python with pandas
installed works. Semantic list-field scoring (--semantic) additionally needs
sentence-transformers + torch; run it via the online-pdf-reader project's
venv, which already has both installed and a PubMedBERT model cached, e.g.:

    "..\\..\\online-pdf-reader\\.venv\\Scripts\\python.exe" score_against_ground_truth.py <predictions.xlsx> --semantic
"""
import argparse
import os
import re
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GROUND_TRUTH_PATH = os.path.join(SCRIPT_DIR, "ground_truth_monograph_extractions.xlsx")
GROUND_TRUTH_SHEET = "Ground Truth"
SAMPLE_CANDIDATES_PATH = os.path.join(SCRIPT_DIR, "gold_sample_candidates.csv")

# Values the pipeline uses to mean "nothing found" -- treated the same as a
# genuinely empty cell on both sides of the comparison.
PLACEHOLDER_PREFIXES = [
    "error", "no_text_found", "section_not_found", "extraction_failed",
    "content_extraction_failed", "summary_generation_failed",
    "no_adverse_events_found", "no date available", "no information",
    "not present in source", "unable to determine", "******", "********",
]

CATEGORICAL_FIELDS = [
    "Liver Function Dose Adjustment", "Kidney Function Dose Adjustment",
    "Pregnancy Recommendation", "Breastfeeding Recommendation",
]
DATE_FIELDS = ["Initial Authorization", "Revision Date"]
LIST_FIELDS = [
    "Indication of Use", "Contraindications", "Serious warning and precautions",
    "Adverse Events", "Drug Interactions",
]
FREETEXT_FIELDS = [
    "Pharmacokinetics", "Metabolism", "Elimination", "Pharmacodynamics",
    "Pregnancy Summary", "Breastfeeding Summary",
]


def is_empty(val):
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    if s == "":
        return True
    return any(s.startswith(p) for p in PLACEHOLDER_PREFIXES)


def norm_scalar(val):
    return re.sub(r"\s+", " ", str(val).strip().lower())


def norm_list(val):
    if is_empty(val):
        return set()
    parts = [re.sub(r"\s+", " ", p.strip().lower()) for p in str(val).split(",")]
    return {p for p in parts if p}


def norm_text_tokens(val):
    if is_empty(val):
        return set()
    return {w for w in re.findall(r"[a-z]{4,}", str(val).lower())}


def _norm_id(s):
    s = re.sub(r"\.pdf$", "", str(s).strip(), flags=re.I)
    return re.sub(r"\s+", " ", s.strip().lower())


# Ground-truth "Drug Name" spelling that doesn't literally match the sample
# list's folder-derived drug_name (British vs American spelling).
DRUG_NAME_ALIASES = {"cephalexin": "cefalexin", "amoxicillin": "amoxicillin trihydrate"}


def _word_bag_key(name):
    """Order/separator-insensitive key: significant words, sorted. Handles
    'Sulfamethoxazole and Trimethoprim' vs 'Trimethoprim-Sulfamethoxazole'."""
    words = re.findall(r"[a-z]{4,}", str(name).lower())
    words = [w for w in words if w != "and"]
    return " ".join(sorted(words))


def _load_pdf_key_by_drug_name():
    """drug_name -> normalized source PDF filename (minus .pdf), from the
    original 53-drug sample list. This is the authoritative filename each
    ground-truth row was actually annotated from. Keyed both by exact name
    and by a word-bag key to survive spelling/ordering differences between
    the folder name and however the ground-truth sheet typed it."""
    try:
        cand = pd.read_csv(SAMPLE_CANDIDATES_PATH)
    except FileNotFoundError:
        return {}, {}
    by_name, by_wordbag = {}, {}
    for _, row in cand.iterrows():
        key = _norm_id(row["chosen_pdf"])
        by_name[row["drug_name"].strip().lower()] = key
        by_wordbag[_word_bag_key(row["drug_name"])] = key
    return by_name, by_wordbag


def match_ids(gt_df, pred_df):
    """Match ground-truth rows to prediction rows by (in priority order):
    1. the original source PDF filename (most reliable -- avoids drift
       between how the ID was hand-typed in the ground-truth sheet vs. the
       pipeline's own ID convention), 2. normalized ID text, 3. Drug Name."""
    gt_df = gt_df.copy()
    pred_df = pred_df.copy()
    pred_df["_key"] = pred_df["ID"].astype(str).apply(_norm_id)
    pdf_key_by_name, pdf_key_by_wordbag = _load_pdf_key_by_drug_name()

    pairs = []
    unmatched = []
    for _, gt_row in gt_df.iterrows():
        hit = pd.DataFrame()
        raw_drug_name = str(gt_row.get("Drug Name", "")).strip()
        drug_name = DRUG_NAME_ALIASES.get(raw_drug_name.lower(), raw_drug_name.lower())
        pdf_key = pdf_key_by_name.get(drug_name) or pdf_key_by_wordbag.get(_word_bag_key(raw_drug_name))
        if pdf_key:
            hit = pred_df[pred_df["_key"] == pdf_key]
        if len(hit) == 0:
            gt_key = _norm_id(gt_row["ID"])
            hit = pred_df[pred_df["_key"] == gt_key]
        if len(hit) == 0 and "Drug Name" in pred_df.columns:
            hit = pred_df[pred_df["Drug Name"].astype(str).str.strip().str.lower() == drug_name]
        if len(hit) == 0:
            unmatched.append(gt_row["ID"])
            continue
        pairs.append((gt_row, hit.iloc[0]))
    return pairs, unmatched


def score(pairs):
    categorical_results = {f: {"correct": 0, "total": 0} for f in CATEGORICAL_FIELDS}
    date_results = {f: {"correct": 0, "total": 0} for f in DATE_FIELDS}
    list_results = {f: {"tp": 0, "fp": 0, "fn": 0, "n": 0} for f in LIST_FIELDS}
    text_results = {f: {"jaccard_sum": 0.0, "n": 0} for f in FREETEXT_FIELDS}
    detail_rows = []

    for gt_row, pred_row in pairs:
        detail = {"ID": gt_row["ID"]}

        for f in CATEGORICAL_FIELDS:
            gt_v, pred_v = gt_row.get(f), pred_row.get(f)
            if is_empty(gt_v):
                continue
            correct = norm_scalar(gt_v) == norm_scalar(pred_v)
            categorical_results[f]["total"] += 1
            categorical_results[f]["correct"] += int(correct)
            detail[f + " match"] = correct

        for f in DATE_FIELDS:
            gt_v, pred_v = gt_row.get(f), pred_row.get(f)
            gt_empty, pred_empty = is_empty(gt_v), is_empty(pred_v)
            date_results[f]["total"] += 1
            if gt_empty:
                correct = pred_empty
            else:
                correct = (not pred_empty) and norm_scalar(gt_v) == norm_scalar(pred_v)
            date_results[f]["correct"] += int(correct)
            detail[f + " match"] = correct

        for f in LIST_FIELDS:
            gt_set = norm_list(gt_row.get(f))
            pred_set = norm_list(pred_row.get(f))
            if not gt_set and not pred_set:
                continue
            extra = pred_set - gt_set      # predicted but not in ground truth (over-generation)
            missing = gt_set - pred_set    # in ground truth but not predicted (under-generation)
            tp = len(gt_set & pred_set)
            fp = len(extra)
            fn = len(missing)
            list_results[f]["tp"] += tp
            list_results[f]["fp"] += fp
            list_results[f]["fn"] += fn
            list_results[f]["n"] += 1
            prec = tp / (tp + fp) if (tp + fp) else None
            rec = tp / (tp + fn) if (tp + fn) else None
            f1 = 2 * prec * rec / (prec + rec) if prec and rec and (prec + rec) else (0.0 if prec is not None and rec is not None else None)
            detail[f + " precision"] = prec
            detail[f + " recall"] = rec
            detail[f + " f1"] = f1
            detail[f + " missing"] = "; ".join(sorted(missing))
            detail[f + " extra"] = "; ".join(sorted(extra))

        for f in FREETEXT_FIELDS:
            gt_tok = norm_text_tokens(gt_row.get(f))
            pred_tok = norm_text_tokens(pred_row.get(f))
            if not gt_tok and not pred_tok:
                continue
            union = gt_tok | pred_tok
            jac = len(gt_tok & pred_tok) / len(union) if union else 0.0
            text_results[f]["jaccard_sum"] += jac
            text_results[f]["n"] += 1
            detail[f + " jaccard"] = jac

        detail_rows.append(detail)

    return categorical_results, date_results, list_results, text_results, detail_rows


def print_report(categorical_results, date_results, list_results, text_results, n_pairs, unmatched):
    print(f"\nScored {n_pairs} matched monographs" + (f" ({len(unmatched)} unmatched: {unmatched})" if unmatched else ""))
    print("\n--- Categorical fields (exact-match accuracy) ---")
    for f, r in categorical_results.items():
        acc = r["correct"] / r["total"] if r["total"] else float("nan")
        print(f"  {f:35s} {r['correct']:3d}/{r['total']:<3d}  acc={acc:.2%}" if r["total"] else f"  {f:35s} no gold labels to score")

    print("\n--- Date fields (exact-match, empty=empty counts as correct) ---")
    for f, r in date_results.items():
        acc = r["correct"] / r["total"] if r["total"] else float("nan")
        print(f"  {f:35s} {r['correct']:3d}/{r['total']:<3d}  acc={acc:.2%}")

    print("\n--- List fields (micro precision/recall/F1 over all matched monographs) ---")
    print("    tp=matched, missing=in truth but not predicted (under-generation), extra=predicted but not in truth (over-generation/hallucination)")
    for f, r in list_results.items():
        tp, fp, fn = r["tp"], r["fp"], r["fn"]
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        rec = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if prec and rec and (prec + rec) else float("nan")
        print(f"  {f:35s} n={r['n']:<3d} tp={tp:<4d} missing(fn)={fn:<4d} extra(fp)={fp:<4d} precision={prec:.2%}  recall={rec:.2%}  F1={f1:.2%}")

    print("\n--- Free-text fields (lexical Jaccard overlap -- ROUGH PROXY ONLY, not semantic quality) ---")
    for f, r in text_results.items():
        avg = r["jaccard_sum"] / r["n"] if r["n"] else float("nan")
        print(f"  {f:35s} n={r['n']:<3d} avg_jaccard={avg:.2%}")


def semantic_list_score(pairs, threshold=0.6, model_name="NeuML/pubmedbert-base-embeddings"):
    """Greedy embedding-similarity matching for list fields, so 'renal
    impairment' and 'kidney disease' can count as a match instead of only
    literal string equality. Requires sentence-transformers (run this via
    the online-pdf-reader project's venv, which already has it + a cached
    PubMedBERT model -- no download, no API calls)."""
    from sentence_transformers import SentenceTransformer
    import numpy as np

    print(f"\nLoading {model_name} for semantic list-field matching...")
    # force CPU: avoids fighting Ollama for scarce GPU VRAM if a local model
    # extraction run happens to be active at the same time
    model = SentenceTransformer(model_name, device="cpu")

    # Collect every unique phrase across all fields/records, embed once.
    all_phrases = set()
    per_pair_lists = []
    for gt_row, pred_row in pairs:
        rec = {}
        for f in LIST_FIELDS:
            gt_set, pred_set = norm_list(gt_row.get(f)), norm_list(pred_row.get(f))
            rec[f] = (gt_set, pred_set)
            all_phrases |= gt_set | pred_set
        per_pair_lists.append(rec)

    all_phrases = list(all_phrases)
    if not all_phrases:
        return {f: {"tp": 0, "fp": 0, "fn": 0} for f in LIST_FIELDS}
    embeddings = model.encode(all_phrases, show_progress_bar=False, batch_size=64)
    emb_by_phrase = dict(zip(all_phrases, embeddings))

    results = {f: {"tp": 0, "fp": 0, "fn": 0} for f in LIST_FIELDS}
    for rec in per_pair_lists:
        for f in LIST_FIELDS:
            gt_set, pred_set = rec[f]
            if not gt_set and not pred_set:
                continue
            gt_list, pred_list = list(gt_set), list(pred_set)
            if gt_list and pred_list:
                g_emb = np.array([emb_by_phrase[p] for p in gt_list])
                p_emb = np.array([emb_by_phrase[p] for p in pred_list])
                sim = model.similarity(p_emb, g_emb)  # shape (pred, gt)
                # greedy max-weight matching: highest similarity pairs first
                flat = sorted(
                    ((sim[i][j].item(), i, j) for i in range(len(pred_list)) for j in range(len(gt_list))),
                    reverse=True,
                )
                used_p, used_g = set(), set()
                tp = 0
                for score_, i, j in flat:
                    if score_ < threshold:
                        break
                    if i in used_p or j in used_g:
                        continue
                    used_p.add(i)
                    used_g.add(j)
                    tp += 1
                results[f]["tp"] += tp
                results[f]["fp"] += len(pred_list) - tp
                results[f]["fn"] += len(gt_list) - tp
            else:
                results[f]["fp"] += len(pred_list)
                results[f]["fn"] += len(gt_list)
    return results


def print_semantic_report(results, threshold):
    print(f"\n--- List fields (SEMANTIC match, PubMedBERT cosine >= {threshold}, greedy matching) ---")
    print("    tp=matched, missing=in truth but not predicted (under-generation), extra=predicted but not in truth (over-generation/hallucination)")
    for f, r in results.items():
        tp, fp, fn = r["tp"], r["fp"], r["fn"]
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        rec = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if prec and rec and (prec + rec) else float("nan")
        print(f"  {f:35s} tp={tp:<4d} missing(fn)={fn:<4d} extra(fp)={fp:<4d} precision={prec:.2%}  recall={rec:.2%}  F1={f1:.2%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions_path")
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default=None, help="Optional path prefix to save detail CSV")
    ap.add_argument("--semantic", action="store_true", help="Also score list fields with PubMedBERT semantic matching (needs sentence-transformers)")
    ap.add_argument("--semantic-threshold", type=float, default=0.6)
    args = ap.parse_args()

    gt_df = pd.read_excel(GROUND_TRUTH_PATH, sheet_name=GROUND_TRUTH_SHEET)
    pred_df = pd.read_excel(args.predictions_path, sheet_name=args.sheet)

    pairs, unmatched = match_ids(gt_df, pred_df)
    if not pairs:
        print("No monographs matched between ground truth and predictions file.", file=sys.stderr)
        sys.exit(1)

    categorical_results, date_results, list_results, text_results, detail_rows = score(pairs)
    print_report(categorical_results, date_results, list_results, text_results, len(pairs), unmatched)

    if args.semantic:
        sem_results = semantic_list_score(pairs, threshold=args.semantic_threshold)
        print_semantic_report(sem_results, args.semantic_threshold)

    if args.out:
        detail_df = pd.DataFrame(detail_rows)
        avg_row = {"ID": "AVERAGE (macro mean across all scored monographs)"}
        for col in detail_df.columns:
            if col == "ID" or col.endswith(" missing") or col.endswith(" extra"):
                continue  # text columns aren't averageable
            vals = detail_df[col].dropna()
            if col.endswith(" match"):
                vals = vals.astype(bool).astype(int)  # True/False -> 1/0
            if len(vals):
                avg_row[col] = vals.mean()
        detail_df = pd.concat([detail_df, pd.DataFrame([avg_row])], ignore_index=True)
        detail_df.to_csv(args.out + "_detail.csv", index=False, encoding="utf-8-sig")
        print(f"\nSaved per-record detail (+ average row) to {args.out}_detail.csv")


if __name__ == "__main__":
    main()
