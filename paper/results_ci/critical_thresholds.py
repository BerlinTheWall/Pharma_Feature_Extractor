"""Critical-item recall at the matching thresholds 0.5, 0.6 and 0.7 (development set).

The critical items are defined as in compute_ci.py (at 0.6); only the matching
of the predictions against them changes with the threshold.
Output: rerun_nov2026/critical_thresholds.csv
"""
import os

import pandas as pd

import compute_ci_rerun  # noqa: F401  (sets the systems of the November runs)
import compute_ci as C

S = C.S
SYSTEMS = ["Llama 3.1 8B, run B (original pipeline)", "Mistral 7B, Nov full context (original pipeline)",
           "Qwen 2.5 7B, Nov full context (original pipeline)", "Llama 3.1 8B, third version",
           "Mistral 7B, third version", "Qwen 2.5 7B, third version"]


def main():
    gt = pd.read_excel(S.GROUND_TRUTH_PATH, sheet_name=S.GROUND_TRUTH_SHEET)
    out = []
    for label in SYSTEMS:
        pairs, _ = S.match_ids(gt, pd.read_excel(os.path.join(C.FINAL, C.SYSTEMS[label])))
        for thr in (0.5, 0.6, 0.7):
            rows = C.per_document(pairs, thr)
            for f in C.CRITICAL_FIELDS:
                tp = sum(r[f + " critical"][0] for r in rows)
                n = sum(r[f + " critical"][1] for r in rows)
                out.append(dict(system=label, field=f, threshold=thr, recall=round(100 * tp / n, 1), n=n))
    df = pd.DataFrame(out)
    df.to_csv(os.path.join(C.HERE, "critical_thresholds.csv"), index=False)
    print(df.pivot_table(index=["system", "field"], columns="threshold", values="recall").to_string())


if __name__ == "__main__":
    main()
