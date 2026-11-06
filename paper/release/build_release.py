"""Build the released dataset from the full-corpus output of the original pipeline.

Changes made to final__monograph_extractions.xlsx:
  * PMS-QUINAPRIL 10mg was saved under both lisinopril and quinapril; the
    lisinopril row is removed (1,433 rows, one per monograph);
  * the option "contrandicated" of the pregnancy and breastfeeding fields is
    spelled "contraindicated";
  * narrow and non-breaking spaces and non-breaking hyphens become normal ones;
  * the two severity columns, which come from another project, are removed;
  * added: the source PDF file, the DIN, the Health Canada PDF link and the
    DPD page, only where they were verified (verify_pdf_links.py, link_verdicts.csv);
  * added: a note for the scanned monographs whose fields come mostly from the
    knowledge of the model and not from the document.

Output: monograph_extractions_release.xlsx and .csv
"""
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(PROJECT, "Received Monographs", "Final extractions", "final__monograph_extractions.xlsx")
TABLE1 = os.path.join(HERE, "..", "table1", "per_document.csv")

SCANNED = {"levofloxacin 500mg", "riva-metoprolol-l 25mg", "riva-metoprolol-l 50mg", "riva-metoprolol-l 100mg"}
SCANNED_NOTE = ("Scanned PDF with almost no text layer: most of the list fields were not taken from "
                "the document and should not be used.")


def clean(v):
    if not isinstance(v, str):
        return v
    v = v.replace(" ", " ").replace(" ", " ").replace("‑", "-")
    return re.sub(r"\bcontrandicated\b", "contraindicated", v, flags=re.I)


def main():
    df = pd.read_excel(SRC)
    df["ID"] = df["ID"].astype(str).str.strip().str.lower()
    dup = df[df["ID"].duplicated(keep=False)]
    assert set(dup["ID"]) == {"pms-quinapril 10mg"}, dup["ID"].tolist()
    df = df[~((df["ID"] == "pms-quinapril 10mg") & (df["Drug Name"] == "Lisinopril"))]
    df = df.drop(columns=["severity_score_percent", "severity_category"])
    df = df.apply(lambda col: col.map(clean))

    t1 = pd.read_csv(TABLE1)
    src_file = {}
    for k in t1.key:
        name = k.split("/")[-1]
        rid = re.sub(r"\.pdf([-_]\d+)\.pdf$", lambda m: m.group(1), name, flags=re.I)
        rid = re.sub(r"\.pdf$", "", rid, flags=re.I).strip().lower()
        src_file[rid] = k

    v = pd.read_csv(os.path.join(HERE, "link_verdicts.csv"), dtype={"din": str}).set_index("ID")
    links = pd.read_csv(os.path.join(HERE, "link_check.csv"), dtype={"din": str}).set_index("ID")
    out = df.rename(columns={"ID": "Monograph ID", "Drug Name": "Generic Drug"})
    ids = out["Monograph ID"]
    out.insert(1, "Source PDF", ids.map(src_file))
    din_ok = ids.map(v["din_ok"]).fillna(False).astype(bool)
    pdf_ok = ids.map(v["pdf_verified"]).fillna(False).astype(bool)
    out["DIN"] = ids.map(v["din"]).where(din_ok)
    out["Monograph PDF (Health Canada)"] = ids.map(v["pdf_url"]).where(pdf_ok)
    out["DPD Product Page"] = ids.map(links["dpd_info_url"]).where(din_ok)
    out["Note"] = ids.map(lambda i: SCANNED_NOTE if i in SCANNED else None)

    assert out["Monograph ID"].is_unique and len(out) == 1433
    assert out["Source PDF"].notna().sum() >= 1432, out[out["Source PDF"].isna()]["Monograph ID"].tolist()
    out.to_excel(os.path.join(HERE, "monograph_extractions_release.xlsx"), index=False)
    out.to_csv(os.path.join(HERE, "monograph_extractions_release.csv"), index=False, encoding="utf-8")
    print(len(out), "rows;", out["DIN"].notna().sum(), "DINs;", out["Monograph PDF (Health Canada)"].notna().sum(),
          "PDF links;", out["Note"].notna().sum(), "scanned notes;", out["Source PDF"].isna().sum(), "without source file")
    print(list(out.columns))


if __name__ == "__main__":
    main()
