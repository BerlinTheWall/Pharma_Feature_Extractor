"""Third version of the extraction pipeline.

Changes from the original pipeline (all decided on the development set):
  * section location from the PDF bookmarks, with a text-search fallback that
    skips the table of contents and cross-references (sections_v3.py);
  * the whole section is used, and long sections are split into pieces that
    are sent to the model one at a time; the answers are merged;
  * serious warnings: the boxed warning when there is one, otherwise the
    Warnings and Precautions section (the original read pages 4 and 6);
  * liver and kidney: the dosage section plus the passages about the liver
    or kidney from the contraindications, warnings and pharmacology sections;
  * pregnancy and breastfeeding: the bookmarked subsection when there is one,
    plus what the contraindications section says about it;
  * cleaning of the answers: duplicates, empty or placeholder items, and
    pieces of a longer item that was split at a comma;
  * the spelling of the option "CONTRAINDICATED" in the prompts.
The model, the temperature (0.1) and the API client are those of the
original pipeline.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AUG_CODE = os.path.join(HERE, "..", "heldout", "runs", "code_aug27")
if AUG_CODE not in sys.path:
    sys.path.insert(0, AUG_CODE)

from pharma_extractor_package.pdf_utils import extract_pdf_text  # noqa: E402
from pharma_extractor_package import pregnancy_extractor as PREG  # noqa: E402
from pharma_extractor_package import breastfeeding_extractor as BF  # noqa: E402

import sections_v3 as SEC  # noqa: E402
import prompts_v3 as P  # noqa: E402

CHUNK = 6000      # characters per piece sent to the model
OVERLAP = 300


def chunks(text, size=CHUNK, overlap=OVERLAP):
    """Split at line breaks into pieces of about `size` characters."""
    if len(text) <= size + size // 3:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            nl = text.rfind("\n", start + size // 2, end)
            if nl > start:
                end = nl
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def tidy(text):
    """Some PDFs come out with a line break after almost every word; join such lines."""
    if not text:
        return text
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if lines and sorted(len(ln.strip()) for ln in lines)[len(lines) // 2] < 20:
        text = re.sub(r"[ \t]*\n[ \t]*(\n[ \t]*)*", " ", text)
        text = re.sub(r"(\w) - (\w)", r"\1-\2", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def get_texts(pdf_path, pages=None):
    """The text given to the model for each field, and how it was found."""
    pages = pages if pages is not None else extract_pdf_text(pdf_path, pages=None)
    full = "\n".join(p["text"] for p in pages)
    t, how = {}, {}
    for f in ("indications", "contraindications", "adverse", "interactions", "dosage", "warnings", "box"):
        t[f], how[f] = SEC.find_section(pdf_path, pages, f)
        t[f] = t[f] or ""

    # No indications heading in the text (it can be an image): use the
    # passages with "indicated" before the contraindications.
    if not t["indications"]:
        cut = full.find(t["contraindications"][:200]) if t["contraindications"] else -1
        t["indications"] = SEC.keyword_passages(full[:cut] if cut > 0 else full[:30000], r"\bindicated\b", width=1200, limit=6000)
        how["indications"] = "passages with 'indicated'" if t["indications"] else None

    # Older monographs have no Drug Interactions section: use the drug
    # interaction passages of Warnings / Precautions.
    if not t["interactions"]:
        t["interactions"] = SEC.keyword_passages(t["warnings"], r"drug\s+interactions?|interact", width=1500, limit=6000)
        how["interactions"] = "passages of warnings section" if t["interactions"] else None

    # Serious warnings: the box if it has real content, else Warnings and Precautions.
    box = t["box"]
    box_body = re.sub(r"^\W*\d*\.?\s*SERIOUS\s+WARNINGS\s+AND\s+PRECAUTIONS(\s+BOX)?", "", box, flags=re.I).strip()
    # Only a separate box section counts (newer monographs: a bookmark, or the
    # heading "3 SERIOUS WARNINGS AND PRECAUTIONS BOX"). In older monographs
    # the boxed text sits inside Warnings and Precautions, and the whole
    # section is used.
    is_box_section = how["box"] == "bookmarks" or re.match(
        r"^\W*\d*\.?\s*SERIOUS\s+WARNINGS\s+AND\s+PRECAUTIONS\s+BOX", box, re.I)
    has_box = bool(is_box_section) and len(re.findall(r"[A-Za-z]{4,}", box_body)) >= 12 and not re.search(
        r"\b(not applicable|there are no serious warnings|none)\b", box_body[:200], re.I)
    t["serious"] = box if has_box else t["warnings"]
    how["serious"] = ("box, " if has_box else "warnings section, ") + str(how["box" if has_box else "warnings"])

    # Liver and kidney: dosage section + organ passages from the rest of Part I.
    other = "\n".join(x for x in (t["contraindications"], t["warnings"]) if x)
    for organ, kw in (("liver", r"hepat|liver|cirrho|child-pugh"), ("kidney", r"\brenal|kidney|creatinine|crcl|glomerular|egfr|dialysis")):
        passages = SEC.keyword_passages(other + "\n" + _pharmacology(full), kw, width=450, limit=7000)
        t[organ] = ("DOSAGE AND ADMINISTRATION:\n" + t["dosage"][:9000] +
                    "\n\nOTHER PASSAGES OF THE MONOGRAPH ABOUT THIS ORGAN:\n" + passages)
        how[organ] = "dosage section + passages"

    # Pregnancy and breastfeeding: the subsection, plus the contraindications.
    for key, title_rx, mod, find_fn, extract_fn in (
        ("pregnancy", r"PREGNAN", PREG, PREG.find_pregnancy_section_pages, PREG.extract_pregnancy_content),
        ("breastfeeding", r"BREAST|NURSING|LACTAT", BF, BF.find_breastfeeding_section_pages, BF.extract_breastfeeding_content),
    ):
        sub = SEC.subsection_by_bookmarks(pdf_path, pages, title_rx)
        src = "bookmarks"
        if not sub or len(sub) < 80:
            try:
                st, en = find_fn(pages, os.path.basename(pdf_path))
                sub = extract_fn(pages, st, en, os.path.basename(pdf_path)) if st else ""
                src = "original method"
            except Exception:
                sub, src = "", None
        if not sub or len(sub) < 80:
            # No subsection: passages that mention it in Part I of the monograph.
            part1 = full[:len(full) * 2 // 3]
            kw = r"pregnan" if key == "pregnancy" else r"breast|nursing|lactat|human milk"
            sub = SEC.keyword_passages(part1, kw, width=500, limit=6000)
            src = "passages" if sub else None
        contra = SEC.keyword_passages(t["contraindications"], title_rx, width=300, limit=2000)
        t[key] = (sub or "")[:12000] + ("\n\nCONTRAINDICATIONS SECTION (passages):\n" + contra if contra else "")
        how[key] = src
    for k in t:
        t[k] = tidy(t[k])
    return t, how


def _pharmacology(full):
    """Special populations passages of the clinical pharmacology part, if present."""
    m = re.search(r"(?m)^\W*(\d{1,2}(\.\d)*\.?\s*)?Special\s+Populations\s+and\s+Conditions", full, re.I)
    return full[m.start():m.start() + 6000] if m else ""


# ---------------- answers ----------------

PLACEHOLDER = re.compile(r"^(\*+|none|n/?a|no_?\w*_found|not (found|applicable|mentioned)|extraction_failed|section_not_found)$", re.I)


def clean_items(raw, drug_name=None):
    if not raw:
        return []
    raw = re.sub(r"(?i)^(here (is|are)[^:]*:|the (list|answer)[^:]*:)", "", raw.strip())
    raw = raw.replace("\n", ",").replace(";", ",")
    items, seen = [], set()
    for it in raw.split(","):
        it = re.sub(r"^[\s\-•*\d.)]+", "", it).strip().strip(".\"'`").strip()
        it = re.sub(r"^(and|or|including|such as)\s+", "", it, flags=re.I).strip()
        # "concomitant_use" -> "concomitant use"; "HereditaryAngioedema" -> "Hereditary Angioedema"
        it = it.replace("_", " ")
        if " " not in it:
            it = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", it)
        if not it or PLACEHOLDER.match(it) or len(it) > 120:
            continue
        if drug_name and it.lower() == str(drug_name).lower():
            continue
        k = it.lower()
        if k not in seen:
            seen.add(k)
            items.append(it)
    return items


def list_field(call, prompt, system, text, drug_name):
    if not text.strip():
        return "SECTION_NOT_FOUND"
    out = []
    for piece in chunks(text):
        ans = call(prompt.format(text=piece), system)
        if ans and ans != "EXTRACTION_FAILED":
            out.extend(clean_items(ans, drug_name))
    seen, merged = set(), []
    for it in out:
        if it.lower() not in seen:
            seen.add(it.lower())
            merged.append(it)
    return ", ".join(merged) if merged else "NONE_FOUND"


def option_field(call, prompt, system, text, options, default):
    if not text.strip():
        return default
    ans = (call(prompt.format(text=text[:20000]), system) or "").strip().strip('".').upper()
    for o in options:  # exact option first, then the first option named in the answer
        if ans == o.upper():
            return o
    hits = [(ans.find(o.upper()), o) for o in options if o.upper() in ans]
    return min(hits)[1] if hits else default


def extract_all(pdf_path, drug_name, call):
    """call(prompt, system) -> str. Returns the row of the nine evaluated fields."""
    pages = extract_pdf_text(pdf_path, pages=None)
    if not pages:
        return {"_error": "NO_TEXT_FOUND"}
    t, how = get_texts(pdf_path, pages)
    row = {
        "Indication of Use": list_field(call, P.INDICATIONS, P.SYS_LIST, t["indications"], drug_name),
        "Contraindications": list_field(call, P.CONTRAINDICATIONS, P.SYS_LIST, t["contraindications"], drug_name),
        "Serious warning and precautions": list_field(
            call, P.BOX if how["serious"].startswith("box") else P.WARNINGS_SECTION, P.SYS_LIST, t["serious"], drug_name),
        "Adverse Events": list_field(call, P.ADVERSE, P.SYS_LIST, t["adverse"], drug_name),
        "Drug Interactions": list_field(call, P.INTERACTIONS.replace("{drug}", str(drug_name)), P.SYS_LIST, t["interactions"], drug_name),
        "Liver Function Dose Adjustment": option_field(call, P.LIVER, P.SYS_OPTION, t["liver"], P.LIVER_OPTIONS, P.LIVER_OPTIONS[1]),
        "Kidney Function Dose Adjustment": option_field(call, P.KIDNEY, P.SYS_OPTION, t["kidney"], P.KIDNEY_OPTIONS, P.KIDNEY_OPTIONS[1]),
        "Pregnancy Recommendation": option_field(call, P.PREGNANCY, P.SYS_OPTION, t["pregnancy"], P.PREGNANCY_OPTIONS, "NO INFORMATION"),
        "Breastfeeding Recommendation": option_field(call, P.BREASTFEEDING, P.SYS_OPTION, t["breastfeeding"], P.BREASTFEEDING_OPTIONS, "NO INFORMATION"),
    }
    row["_sections"] = "; ".join(f"{k}={v}" for k, v in how.items())
    return row
