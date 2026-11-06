"""Error analysis of the list fields on the development set (Set A).

For every gold item the model missed and every item it added, look at the
text the pipeline gave the model and at the whole document:

  missed, in the given text      the right text was given, the model left it out
  missed, not in the given text  the item is elsewhere in the document (wrong or partial section)
  missed, not found in the text  no close wording anywhere in the extracted text
  added, in the given text       the model listed something that is in the text but not in the gold list
  added, not in the given text   no close wording in the text the model saw

Items are matched exactly as in compute_ci.py (PubMedBERT, threshold 0.6).
"Close wording" = at least 75% of the item's words (4+ letters) appear in the
text, comparing the first 6 letters of each word, so "hypersensitivity"
matches "hypersensitive".

Run with online-pdf-reader\\.venv python from this folder.
Output: rerun_nov2026/error_items_final.csv and rerun_nov2026/error_summary_final.csv
(original pipeline against the final, third version).
"""
import contextlib
import io
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "heldout", "runs")
FE = r"D:\Western University\Project\Received Monographs\Final extractions"
sys.path.insert(0, os.path.join(RUNS, "code_aug27"))
sys.path.insert(0, RUNS)
sys.path.insert(0, HERE)
import pharma_extractor_package as pkg  # noqa: E402  (August code first)
assert os.path.abspath(pkg.__file__).startswith(os.path.abspath(os.path.join(RUNS, "code_aug27")))
from pharma_extractor_package.pdf_utils import extract_pdf_text  # noqa: E402
from pharma_extractor_package.config import WARNINGS_PAGES  # noqa: E402
from pharma_extractor_package import indications_extractor as IND  # noqa: E402
from pharma_extractor_package import contraindications_extractor as CI  # noqa: E402
from pharma_extractor_package import adverse_events_extractor as AE  # noqa: E402
from pharma_extractor_package import drug_interactions_extractor as DI  # noqa: E402
import run_setB  # noqa: E402
import compute_ci as C  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "v3"))
import pipeline_v3 as V3  # noqa: E402

S = C.S
sys.stdout.reconfigure(encoding="utf-8")
OUT = os.path.join(HERE, "rerun_nov2026")

FIELDS = ["Indication of Use", "Contraindications", "Adverse Events", "Drug Interactions",
          "Serious warning and precautions"]
V3_OUT = os.path.join(HERE, "..", "v3", "setA_outputs")
SYSTEMS = {
    "Qwen 2.5 7B, original": os.path.join(RUNS, "setA_outputs", "qwen_v1_setA.xlsx"),
    "Qwen 2.5 7B, final version": os.path.join(V3_OUT, "qwen_v3_setA.xlsx"),
    "Mistral 7B, original": os.path.join(RUNS, "setA_outputs", "mistral_v1_setA.xlsx"),
    "Mistral 7B, final version": os.path.join(V3_OUT, "mistral_v3_setA.xlsx"),
    "Llama 3.1 8B run B, original": os.path.join(FE, "cf_llama_extractions.xlsx"),
    "Llama 3.1 8B, final version": os.path.join(V3_OUT, "llama_v3_setA.xlsx"),
}
V3_KEY = {"Indication of Use": "indications", "Contraindications": "contraindications",
          "Adverse Events": "adverse", "Drug Interactions": "interactions",
          "Serious warning and precautions": "serious"}


def v1_text(field, pages, path, name):
    if field == "Indication of Use":
        st, n = IND.find_indications_section_pages(pages, name)
        if not st:
            return ""
        return (IND.extract_indications_content(pages, st, IND.find_next_section_page(pages, st, n, name), name) or "")[:15000]
    if field == "Contraindications":
        st, n = CI.find_contraindications_section_pages(pages, name)
        if not st:
            return ""
        en = CI.find_next_section_page_contraindications(pages, st, n, name)
        return (CI.extract_contraindications_content(pages, st, en, name) or "")[:15000]
    if field == "Adverse Events":
        st, en = AE.get_adverse_reactions_range(pages, name)
        return AE.extract_adverse_reactions_section(pages, st, en) or ""
    if field == "Drug Interactions":
        st, n = DI.find_drug_interactions_section_pages(pages, name)
        if not st:
            return ""
        return DI.extract_drug_interactions_content(pages, st, DI.find_next_section_page(pages, st, n, name), name) or ""
    return (extract_pdf_text(path, pages=WARNINGS_PAGES) or "")[:15000]


def stems(s):
    return [w[:6] for w in re.findall(r"[a-z]{4,}", s.lower())]


def close_in(item, text_stems):
    w = stems(item)
    return bool(w) and sum(x in text_stems for x in w) / len(w) >= 0.75


def match(pred, gold, thr=0.6):
    """Same greedy one-to-one matching as compute_ci.greedy_match, returning both sides."""
    if not pred or not gold:
        return set(), set()
    sim = C.embed(pred) @ C.embed(gold).T
    order = sorted(((sim[i, j], i, j) for i in range(len(pred)) for j in range(len(gold))), reverse=True)
    up, ug = set(), set()
    for s, i, j in order:
        if s < thr:
            break
        if i in up or j in ug:
            continue
        up.add(i)
        ug.add(j)
    return {pred[i] for i in up}, {gold[j] for j in ug}


def main():
    gt = pd.read_excel(run_setB.SETA_KEY, sheet_name="Ground Truth")
    paths = {it["id"]: it["path"] for it in run_setB.set_a_items()}
    texts = {}
    for gid, path in paths.items():
        with contextlib.redirect_stdout(io.StringIO()):
            pages = extract_pdf_text(path, pages=None)
            full = "\n".join(p["text"] for p in pages)
            for f in FIELDS:
                texts[(gid, f, "v1")] = v1_text(f, pages, path, gid)
            t3, _ = V3.get_texts(path, pages)
            for f in FIELDS:
                texts[(gid, f, "v3")] = t3[V3_KEY[f]]
        texts[(gid, "full")] = full
    stem_cache = {k: set(stems(v)) for k, v in texts.items()}

    rows = []
    for system, fpath in SYSTEMS.items():
        version = "v3" if "final" in system else "v1"
        pred_df = pd.read_excel(fpath)
        pairs, _unmatched = S.match_ids(gt, pred_df)
        for g, p in pairs:
            gid = str(g["ID"])
            for f in FIELDS:
                gold, pred = sorted(S.norm_list(g.get(f))), sorted(S.norm_list(p.get(f)))
                mp, mg = match(pred, gold)
                given, full = stem_cache[(gid, f, version)], stem_cache[(gid, "full")]
                for it in gold:
                    if it in mg:
                        kind = "correct"
                    elif close_in(it, given):
                        kind = "missed, in the given text"
                    elif close_in(it, full):
                        kind = "missed, not in the given text"
                    else:
                        kind = "missed, not found in the text"
                    rows.append(dict(system=system, id=gid, field=f, item=it, kind=kind))
                for it in pred:
                    if it in mp:
                        continue
                    kind = "added, in the given text" if close_in(it, given) else "added, not in the given text"
                    rows.append(dict(system=system, id=gid, field=f, item=it, kind=kind))
    items = pd.DataFrame(rows)
    items.to_csv(os.path.join(OUT, "error_items_final.csv"), index=False)
    summary = items.groupby(["system", "field", "kind"]).size().unstack(fill_value=0)
    summary.to_csv(os.path.join(OUT, "error_summary_final.csv"))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print(summary.to_string())
    print()
    print(items.groupby(["field", "kind"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
