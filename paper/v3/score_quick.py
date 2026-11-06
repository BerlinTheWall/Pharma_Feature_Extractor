"""Quick scores on the development set (no intervals), for comparing versions.

Same matching as results_ci/compute_ci.py (PubMedBERT, 0.6, one-to-one) and
the same accuracy for the categorical fields (with the spelling fix).
Usage: python score_quick.py file1.xlsx file2.xlsx ...
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "results_ci"))
import compute_ci as C  # noqa: E402

S = C.S


def scores(path):
    gt = pd.read_excel(os.path.join(C.FINAL, "ground_truth_monograph_extractions_FROZEN_2026-10-05.xlsx"),
                       sheet_name="Ground Truth")
    pairs, unmatched = S.match_ids(gt, pd.read_excel(path))
    out = {"n": len(pairs)}
    rows = C.per_document(pairs, 0.6)
    for f in S.LIST_FIELDS:
        tp = sum(r[f][0] for r in rows); fp = sum(r[f][1] for r in rows); fn = sum(r[f][2] for r in rows)
        p, r_, f1 = C.prf(tp, fp, fn)
        out[f[:12] + " R"] = round(100 * r_, 1)
        out[f[:12] + " P"] = round(100 * p, 1)
    for f in C.CRITICAL_FIELDS:
        a = [r[f + " critical"] for r in rows]
        out[f[:12] + " crit"] = round(100 * sum(x[0] for x in a) / max(1, sum(x[1] for x in a)), 1)
    _, _, _, _, detail = S.score(pairs)
    for f in S.CATEGORICAL_FIELDS:
        v = [bool(d[f + " match"]) for d in detail if d.get(f + " match") is not None]
        out[f[:12] + " acc"] = round(100 * sum(v) / len(v), 1)
    return out


if __name__ == "__main__":
    res = {os.path.basename(p): scores(p) for p in sys.argv[1:]}
    pd.set_option("display.width", 250)
    print(pd.DataFrame(res).to_string())
