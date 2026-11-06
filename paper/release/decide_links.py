"""Decide which links and DINs are kept in the released data.

Inputs: link_check.csv (check_links.py) and pdf_link_check.csv (verify_pdf_links.py).
A Health Canada PDF link is kept when the downloaded monograph is
  * the same file as our copy, or
  * the same monograph with a close text (similarity >= 0.8), or
  * a monograph whose first pages name both the brand and the company of the row.
A DIN (and its DPD page) is kept only when the PDF link is kept, the strength
in the file name matches the DPD record, and the DPD company or brand matches.

Output: link_verdicts.csv
"""
import json
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(PROJECT, "Received Monographs", "Final extractions", "final__monograph_extractions.xlsx")
STOP = {"inc", "ltd", "limited", "ltee", "ltée", "incorporated", "corp", "corporation", "canada", "pharma",
        "pharmaceuticals", "pharmaceutical", "ulc", "health", "the", "laboratories", "co"}


def norm(s):
    return re.sub(r"[\s\-‐‑]+", " ", str(s).lower())


def names_found(row, text):
    t = norm(text)
    brand = norm(row["Brand Name"]).strip()
    company = [w for w in re.findall(r"[a-zé]{3,}", str(row["Company"]).lower()) if w not in STOP]
    return bool(brand) and brand in t and ((not company) or any(w in t for w in company))


def main():
    p = pd.read_csv(os.path.join(HERE, "pdf_link_check.csv"))
    cache = json.load(open(os.path.join(HERE, "pdf_check_cache.json"), encoding="utf-8"))
    rows = pd.read_excel(SRC).drop_duplicates("ID", keep="last")
    rows["ID"] = rows["ID"].astype(str).str.strip().str.lower()
    p = p.merge(rows[["ID", "Brand Name", "Company"]], on="ID", how="left")
    p["names_found"] = [names_found(r, cache.get(r["pdf_url"], {}).get("text", "")) if isinstance(r["pdf_url"], str) else False
                        for _, r in p.iterrows()]
    p["pdf_verified"] = ((p.verdict == "same file") | ((p.verdict == "same monograph") & (p.similarity >= 0.8))
                         | ((p.verdict != "no link") & p.names_found))
    links = pd.read_csv(os.path.join(HERE, "link_check.csv"), dtype={"din": str})
    m = p.merge(links[["ID", "din", "company_ok", "brand_ok", "strength_ok"]], on="ID")
    m["din_ok"] = m.pdf_verified & m.strength_ok & (m.company_ok | m.brand_ok)
    m.to_csv(os.path.join(HERE, "link_verdicts.csv"), index=False)
    print("PDF links kept:", int(m.pdf_verified.sum()), "of", len(m), "| DINs kept:", int(m.din_ok.sum()))
    print(pd.crosstab(m.verdict, m.pdf_verified))


if __name__ == "__main__":
    main()
