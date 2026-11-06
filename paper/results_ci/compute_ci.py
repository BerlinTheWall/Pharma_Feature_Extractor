"""
Confidence intervals for the development-set results.

Reuses the project's own scoring code (score_against_ground_truth.py) so the
point estimates match the numbers already reported, then adds:
  - 95% bootstrap intervals over monographs for list-field precision/recall/F1
    (items inside one monograph are not independent, so monographs are resampled),
  - 95% Wilson intervals for categorical accuracy,
  - critical-item recall with a bootstrap interval,
  - the paired original-vs-second-version difference in recall per monograph,
  - a sensitivity check of the semantic threshold (0.5, 0.6, 0.7).

Run with the environment that has sentence-transformers:
  "..\\..\\..\\online-pdf-reader\\.venv\\Scripts\\python.exe" compute_ci.py
"""

import json
import math
import os
import sys

import numpy as np
import pandas as pd

FINAL = r"d:\Western University\Project\Received Monographs\Final extractions"
sys.path.insert(0, FINAL)
import score_against_ground_truth as S  # noqa: E402

# The original pregnancy and breastfeeding prompts spell the option
# "CONTRANDICATED", while the gold standard says "CONTRAINDICATED". It is the
# same option, so the scorer treats the two spellings as equal (fixed
# 2026-11-06; before this, every such answer was scored as wrong).
_norm_scalar_original = S.norm_scalar


def _norm_scalar_fixed(val):
    return _norm_scalar_original(val).replace("contrandicated", "contraindicated")


S.norm_scalar = _norm_scalar_fixed

HERE = os.path.dirname(os.path.abspath(__file__))
N_BOOT = 10000
SEED = 20261005
THRESHOLDS = (0.5, 0.6, 0.7)
CRITICAL_FIELDS = ["Adverse Events", "Contraindications"]
WARNINGS = "Serious warning and precautions"

# Result files as they exist on disk. Labels describe the file, nothing more.
SYSTEMS = {
    "Llama 3.1 8B, full-corpus run (original pipeline)": "final__monograph_extractions - lowercased .xlsx",
    "Llama 3.1 8B, Aug 27 run (original pipeline)": "cf_llama_extractions.xlsx",
    "Llama 3.1 8B, Aug 27 run (second version)": "cf_llama_v2_extractions.xlsx",
    "Mistral 7B (original pipeline)": "mistral_extractions.xlsx",
    "Qwen 2.5 7B (original pipeline)": "qwen_extractions.xlsx",
    "Qwen 2.5 7B (second version)": "qwen_v2_extractions.xlsx",
}
PAIRS = [
    ("Qwen 2.5 7B", "Qwen 2.5 7B (original pipeline)", "Qwen 2.5 7B (second version)"),
    ("Llama 3.1 8B, Aug 27 run", "Llama 3.1 8B, Aug 27 run (original pipeline)",
     "Llama 3.1 8B, Aug 27 run (second version)"),
]
PAIRED_FIELDS = ["Indication of Use", "Contraindications", "Adverse Events", "Drug Interactions"]

_model = None
_cache = {}


def embed(phrases):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("NeuML/pubmedbert-base-embeddings", device="cpu")
    new = [p for p in phrases if p not in _cache]
    if new:
        for p, e in zip(new, _model.encode(new, show_progress_bar=False, batch_size=64, normalize_embeddings=True)):
            _cache[p] = e
    return np.array([_cache[p] for p in phrases])


def greedy_match(pred, gold, threshold):
    """Same one-to-one greedy matching as semantic_list_score. Returns (tp, matched gold items)."""
    if not pred or not gold:
        return 0, set()
    sim = embed(pred) @ embed(gold).T
    order = sorted(((sim[i, j], i, j) for i in range(len(pred)) for j in range(len(gold))), reverse=True)
    used_p, used_g = set(), set()
    for s, i, j in order:
        if s < threshold:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
    return len(used_g), {gold[j] for j in used_g}


def critical_items(gt_row, field, threshold=0.6):
    warn, items = sorted(S.norm_list(gt_row.get(WARNINGS))), sorted(S.norm_list(gt_row.get(field)))
    if not warn or not items:
        return set()
    sim = embed(items) @ embed(warn).T
    return {items[i] for i in range(len(items)) if sim[i].max() >= threshold}


def per_document(pairs, threshold):
    """One dict per monograph: tp/fp/fn per list field, plus critical-item counts."""
    rows = []
    for gt_row, pred_row in pairs:
        rec = {}
        for f in S.LIST_FIELDS:
            gold, pred = sorted(S.norm_list(gt_row.get(f))), sorted(S.norm_list(pred_row.get(f)))
            tp, matched = greedy_match(pred, gold, threshold)
            rec[f] = (tp, len(pred) - tp, len(gold) - tp)
            if f in CRITICAL_FIELDS:
                # As in critical_item_recall.py: predictions are matched against
                # the critical gold items alone.
                crit = sorted(critical_items(gt_row, f))
                rec[f + " critical"] = (greedy_match(pred, crit, threshold)[0], len(crit))
        rows.append(rec)
    return rows


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p + r and not math.isnan(p + r) else float("nan")
    return p, r, f


def boot_ci(values_fn, n, rng):
    stats = np.array([values_fn(rng.integers(0, n, n)) for _ in range(N_BOOT)], dtype=float)
    return [float(x) for x in np.nanpercentile(stats, [2.5, 97.5], axis=0).T.reshape(-1)]


def wilson(k, n, z=1.959964):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main():
    gt = pd.read_excel(S.GROUND_TRUTH_PATH, sheet_name=S.GROUND_TRUTH_SHEET)
    rng = np.random.default_rng(SEED)
    out, docs_by_system = [], {}

    for label, fname in SYSTEMS.items():
        pred = pd.read_excel(os.path.join(FINAL, fname))
        pairs, unmatched = S.match_ids(gt, pred)
        print(f"{label}: {len(pairs)} matched, {len(unmatched)} unmatched", flush=True)
        _, _, _, _, detail = S.score(pairs)

        for f in S.CATEGORICAL_FIELDS:
            vals = [d.get(f + " match") for d in detail]
            vals = [bool(v) for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
            k, n = sum(vals), len(vals)
            lo, hi = wilson(k, n)
            out.append(dict(system=label, field=f, metric="accuracy", n=n, value=k / n if n else None, lo=lo, hi=hi))

        for thr in THRESHOLDS:
            rows = per_document(pairs, thr)
            if thr == 0.6:
                docs_by_system[label] = {S._norm_id(g["ID"]): r for (g, _), r in zip(pairs, rows)}
            for f in S.LIST_FIELDS:
                arr = np.array([r[f] for r in rows])
                p, r_, f1 = prf(*arr.sum(axis=0))
                if thr != 0.6:
                    out.append(dict(system=label, field=f, metric=f"recall@{thr}", n=len(rows), value=r_))
                    out.append(dict(system=label, field=f, metric=f"f1@{thr}", n=len(rows), value=f1))
                    continue
                ci = boot_ci(lambda idx: prf(*arr[idx].sum(axis=0)), len(rows), rng)
                for name, val, (lo, hi) in zip(("precision", "recall", "f1"), (p, r_, f1),
                                               (ci[0:2], ci[2:4], ci[4:6])):
                    out.append(dict(system=label, field=f, metric=name, n=len(rows), value=val, lo=lo, hi=hi))
            if thr == 0.6:
                for f in CRITICAL_FIELDS:
                    arr = np.array([r[f + " critical"] for r in rows])
                    tot = arr.sum(axis=0)
                    val = tot[0] / tot[1] if tot[1] else float("nan")
                    lo, hi = boot_ci(lambda idx: (lambda s: s[0] / s[1] if s[1] else np.nan)(arr[idx].sum(axis=0)),
                                     len(rows), rng)
                    out.append(dict(system=label, field=f, metric="critical recall", n=int(tot[1]),
                                    value=val, lo=lo, hi=hi))

    paired = []
    for name, a, b in PAIRS:
        ids = sorted(set(docs_by_system[a]) & set(docs_by_system[b]))
        for f in PAIRED_FIELDS:
            A = np.array([docs_by_system[a][i][f] for i in ids])
            B = np.array([docs_by_system[b][i][f] for i in ids])
            rec = lambda X: X[:, 0].sum() / max(X[:, 0].sum() + X[:, 2].sum(), 1)
            f1 = lambda X: prf(*X.sum(axis=0))[2]
            lo_r, hi_r = boot_ci(lambda idx: rec(B[idx]) - rec(A[idx]), len(ids), rng)
            lo_f, hi_f = boot_ci(lambda idx: f1(B[idx]) - f1(A[idx]), len(ids), rng)
            dA = A[:, 0] / np.maximum(A[:, 0] + A[:, 2], 1)
            dB = B[:, 0] / np.maximum(B[:, 0] + B[:, 2], 1)
            try:
                from scipy.stats import wilcoxon
                pval = float(wilcoxon(dB, dA, zero_method="wilcox").pvalue) if np.any(dB != dA) else 1.0
            except Exception:
                pval = None
            paired.append(dict(model=name, field=f, n=len(ids),
                               recall_before=rec(A), recall_after=rec(B), recall_diff=rec(B) - rec(A),
                               recall_diff_lo=lo_r, recall_diff_hi=hi_r,
                               f1_before=f1(A), f1_after=f1(B), f1_diff=f1(B) - f1(A),
                               f1_diff_lo=lo_f, f1_diff_hi=hi_f,
                               improved=int((dB > dA).sum()), worse=int((dB < dA).sum()),
                               wilcoxon_p=pval))

    pd.DataFrame(out).to_csv(os.path.join(HERE, "development_results_with_ci.csv"), index=False)
    pd.DataFrame(paired).to_csv(os.path.join(HERE, "paired_version_comparison.csv"), index=False)
    with open(os.path.join(HERE, "run_info.json"), "w") as fh:
        json.dump({"n_boot": N_BOOT, "seed": SEED, "thresholds": THRESHOLDS, "systems": SYSTEMS}, fh, indent=2)
    print("done")


if __name__ == "__main__":
    main()
