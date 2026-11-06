"""Check that each monograph's Health Canada PDF link leads to the same monograph.

For every distinct pdf_url in pdf_links_cache.json, the PDF is downloaded and
compared with the local PDF of each row that uses it:
  same file        identical SHA-256
  same monograph   different file, but the text of the first pages is close
                   (the monograph was probably revised after January 2026)
  different        the text of the first pages is not close
The downloads are kept only as hashes and first-page text (pdf_check_cache.json).

Output: pdf_link_check.csv
Usage: python verify_pdf_links.py
"""
import difflib
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import urllib.request
import warnings

import pandas as pd
import PyPDF2

logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CORPUS = os.path.join(PROJECT, "Received Monographs", "Product monograph")
LINKS = os.path.join(PROJECT, "phara_monograph_visualization ___", "pdf_links_cache.json")
TABLE1 = os.path.join(HERE, "..", "table1", "per_document.csv")
CACHE = os.path.join(HERE, "pdf_check_cache.json")
UA = {"User-Agent": "monograph-research/1.0"}


def first_text(data, pages=3):
    try:
        r = PyPDF2.PdfReader(io.BytesIO(data))
        t = " ".join((r.pages[i].extract_text() or "") for i in range(min(pages, len(r.pages))))
    except Exception:  # noqa: BLE001
        t = ""
    return re.sub(r"\s+", " ", t.lower())[:6000]


def similar(a, b):
    if not a or not b:
        return 0.0
    wa, wb = re.findall(r"[a-z]{3,}", a), re.findall(r"[a-z]{3,}", b)
    return difflib.SequenceMatcher(None, wa[:600], wb[:600], autojunk=False).ratio()


def main():
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    links = json.load(open(LINKS, encoding="utf-8"))
    t1 = pd.read_csv(TABLE1)
    # "AMLODIPINE 10mg.pdf-2.pdf" is the row "amlodipine 10mg-2"
    local = {}
    for k in t1.key:
        name = k.split("/")[-1]
        name = re.sub(r"\.pdf([-_]\d+)\.pdf$", lambda m: m.group(1), name, flags=re.I)
        name = re.sub(r"\.pdf$", "", name, flags=re.I)
        local[name.strip().lower()] = os.path.join(CORPUS, k)

    for i, url in enumerate(sorted({v["pdf_url"] for v in links.values() if v.get("pdf_url")})):
        if url in cache:
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            cache[url] = {"sha256": hashlib.sha256(data).hexdigest(), "text": first_text(data)}
        except Exception as e:  # noqa: BLE001
            cache[url] = {"error": str(e)}
        time.sleep(0.3)
        if i % 25 == 0:
            print(i, flush=True)
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"))

    rows, local_memo = [], {}
    for mid, v in links.items():
        path = local.get(mid)
        url = v.get("pdf_url")
        if path not in local_memo and path:
            data = open(path, "rb").read()
            local_memo[path] = (hashlib.sha256(data).hexdigest(), first_text(data))
        lh, lt = local_memo.get(path, (None, ""))
        remote = cache.get(url, {}) if url else {}
        if not url:
            verdict, sim = "no link", None
        elif "error" in remote:
            verdict, sim = "download failed", None
        elif remote["sha256"] == lh:
            verdict, sim = "same file", 1.0
        else:
            sim = similar(lt, remote["text"])
            verdict = "same monograph" if sim >= 0.6 else "different"
        rows.append(dict(ID=mid, local_found=bool(path), pdf_url=url, verdict=verdict,
                         similarity=None if sim is None else round(sim, 3)))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "pdf_link_check.csv"), index=False)
    print(out.verdict.value_counts())


if __name__ == "__main__":
    main()
