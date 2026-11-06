"""Check the DIN and links of every monograph against the Drug Product Database.

The links come from phara_monograph_visualization ___/pdf_links_cache.json,
where 248 of the 1,433 monographs were matched by a fuzzy name match. For each
monograph, the DIN is looked up in the DPD API, and its company, brand name
and strength are compared with the monograph.

Output: link_check.csv (one row per monograph) and dpd_api_cache.json.
"""
import json
import os
import re
import time
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LINKS = os.path.join(PROJECT, "phara_monograph_visualization ___", "pdf_links_cache.json")
DATA = os.path.join(PROJECT, "Received Monographs", "Final extractions", "final__monograph_extractions.xlsx")
CACHE = os.path.join(HERE, "dpd_api_cache.json")
API = "https://health-products.canada.ca/api/drug/{}/?{}&lang=en&type=json"

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def api(kind, query):
    key = f"{kind}?{query}"
    if key not in cache:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(API.format(kind, query), timeout=30) as r:
                    cache[key] = json.loads(r.read().decode("utf-8"))
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    cache[key] = {"error": str(e)}
                time.sleep(2)
        time.sleep(0.2)
    return cache[key]


STOP = {"inc", "ltd", "limited", "limitee", "ltee", "incorporated", "corp", "corporation", "co", "the",
        "canada", "pharma", "pharmaceuticals", "pharmaceutical", "ulc", "ltd.", "llc", "gmbh", "sa", "ag"}


def words(s):
    s = str(s).lower().replace("é", "e")
    return {w for w in re.findall(r"[a-z0-9]+", s) if w not in STOP and len(w) > 1}


def same_company(a, b):
    wa, wb = words(a), words(b)
    return bool(wa & wb)


def strengths_in(text):
    """Numbers written in the file name, e.g. '10mg' -> {'10'}, '- 2.5' -> {'2.5'}."""
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in re.findall(r"\d+(?:\.\d+)?", str(text))}


def main():
    links = json.load(open(LINKS, encoding="utf-8"))
    data = pd.read_excel(DATA)
    data = data.drop_duplicates("ID", keep="last")  # pms-quinapril 10mg is listed twice
    rows = []
    for i, r in enumerate(data.itertuples(index=False)):
        mid = str(r.ID).strip().lower()
        link = links.get(mid, {})
        prod = api("drugproduct", f"din={link.get('din')}") if link.get("din") else []
        prod = prod[0] if isinstance(prod, list) and prod else {}
        ais = api("activeingredient", f"id={prod['drug_code']}") if prod.get("drug_code") else []
        dpd_strengths = {(a.get("strength") or "").rstrip("0").rstrip(".") if "." in (a.get("strength") or "") else (a.get("strength") or "")
                         for a in ais} if isinstance(ais, list) else set()
        file_strengths = strengths_in(re.sub(r"[-_ ]2$", "", mid))  # '-2' marks a second copy, not a strength
        company_ok = same_company(r.Company, prod.get("company_name", ""))
        brand_ok = bool(words(r._1) & words(prod.get("brand_name", ""))) or bool(words(mid) & words(prod.get("brand_name", "")))
        strength_ok = (not file_strengths) or bool(file_strengths & dpd_strengths)
        rows.append(dict(
            ID=mid, brand=r._1, company=r.Company, din=link.get("din"), match_score=link.get("match_score"),
            dpd_brand=prod.get("brand_name"), dpd_company=prod.get("company_name"),
            dpd_strengths=";".join(sorted(dpd_strengths)), file_strengths=";".join(sorted(file_strengths)),
            company_ok=company_ok, brand_ok=brand_ok, strength_ok=strength_ok,
            pdf_url=link.get("pdf_url"), dpd_info_url=link.get("dpd_info_url")))
        if i % 100 == 0:
            print(i, flush=True)
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    out = pd.DataFrame(rows)
    out["all_ok"] = out.company_ok & out.brand_ok & out.strength_ok
    out.to_csv(os.path.join(HERE, "link_check.csv"), index=False)
    fuzzy = out.match_score < 1
    print(pd.crosstab(fuzzy.rename("fuzzy"), out.all_ok))
    print(out[~out.all_ok][["company_ok", "brand_ok", "strength_ok"]].value_counts())


if __name__ == "__main__":
    main()
