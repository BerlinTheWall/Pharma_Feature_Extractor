"""How much of the gold list is in the text given to the model, for v1, v2 and v3.

No model is called. For each development monograph and list field, counts
the gold items whose words appear in the given text (same check as
results_ci/error_analysis.py) and the length of that text.
Run with online-pdf-reader\\.venv python. Use --set B only for section
statistics without gold (lengths and how each section was found).
"""
import argparse
import contextlib
import io
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "results_ci"))
import error_analysis as E  # noqa: E402  (loads the August code first)
import pipeline_v3 as V3  # noqa: E402

MAP = {"Indication of Use": "indications", "Contraindications": "contraindications",
       "Serious warning and precautions": "serious", "Adverse Events": "adverse", "Drug Interactions": "interactions"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()
    gt = pd.read_excel(E.run_setB.SETA_KEY, sheet_name="Ground Truth")
    gt["k"] = gt["ID"].astype(str)
    rows = []
    for it in E.run_setB.set_a_items():
        g = gt[gt.k == it["id"]].iloc[0]
        with contextlib.redirect_stdout(io.StringIO()):
            pages = E.extract_pdf_text(it["path"], pages=None)
            full = "\n".join(p["text"] for p in pages)
            t3, how = V3.get_texts(it["path"], pages)
            for f, k in MAP.items():
                gold = E.S.norm_list(g.get(f))
                for v, txt in (("v1", E.v1_text(f, pages, it["path"], it["id"])),
                               ("v2", E.v2_text(f, pages, full, it["path"], it["id"])),
                               ("v3", t3[k])):
                    st = set(E.stems(txt))
                    rows.append(dict(id=it["id"][:28], field=f, version=v, gold=len(gold),
                                     covered=sum(E.close_in(x, st) for x in gold), chars=len(txt),
                                     how=how.get(k) if v == "v3" else ""))
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(HERE, "check_sections.csv"), index=False)
    s = d.groupby(["field", "version"]).agg(gold=("gold", "sum"), covered=("covered", "sum"),
                                            median_chars=("chars", "median"), max_chars=("chars", "max"))
    s["share"] = (s.covered / s.gold * 100).round(1)
    pd.set_option("display.width", 200)
    print(s.to_string())
    if args.detail:
        p = d.pivot_table(index=["field", "id"], columns="version", values="covered")
        p["gold"] = d[d.version == "v3"].set_index(["field", "id"])["gold"]
        p["how"] = d[d.version == "v3"].set_index(["field", "id"])["how"]
        print(p[(p["v3"] < p[["v1", "v2"]].max(axis=1)) | (p["v3"] < p["gold"] * 0.8)].to_string())


if __name__ == "__main__":
    main()
