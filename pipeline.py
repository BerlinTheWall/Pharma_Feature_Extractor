"""Main pipeline for processing pharmaceutical monographs."""

import os
import time
import pandas as pd
from typing import List, Dict

from .config import SAFE_DELAY, OUTPUT_COLUMN_ORDER, EXCEL_FLUSH_EVERY
from .checkpoint import (
    append_record,
    completed_keys,
    failed_keys,
    load_records,
    rewrite_records,
)
from .metadata_extractor import extract_metadata
from .adverse_events_extractor import extract_adverse_events
from .drug_interactions_extractor import extract_drug_interactions_from_pdf
from .indications_extractor import extract_indications_from_pdf
from .warnings_extractor import extract_warnings_from_pdf
from .liver_extractor import extract_liver_dose_adjustment_from_pdf
from .kidney_extractor import extract_kidney_dose_adjustment_from_pdf
from .pharmacokinetics_extractor import extract_pharmacokinetics_from_pdf
from .metabolism_extractor import extract_metabolism_from_pdf
from .elimination_extractor import extract_elimination_from_pdf
from .pharmacodynamics_extractor import extract_pharmacodynamics_from_pdf
from .pregnancy_extractor import extract_pregnancy_from_pdf
from .breastfeeding_extractor import extract_breastfeeding_from_pdf
from .contraindications_extractor import extract_contraindications_from_pdf


def get_pdf_files(target_folder: str, recursive: bool = True) -> List[Dict]:
    """
    Find the PDFs to process.

    The corpus is nested as <class>/<generic>/*.pdf, so a full run walks the
    tree rather than a single directory. Each entry carries a `key` -- the path
    relative to target_folder -- which identifies the file in the checkpoint.
    A bare filename would not: the same filename recurs under different
    therapeutic classes.

    Returns:
        List of {"path", "key", "filename"} dicts, sorted so a resumed run
        walks the corpus in the same order as the original.
    """
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return []

    entries = []
    if recursive:
        for dirpath, _dirnames, filenames in os.walk(target_folder):
            for filename in filenames:
                if filename.lower().endswith(".pdf"):
                    full_path = os.path.join(dirpath, filename)
                    key = os.path.relpath(full_path, target_folder).replace(os.sep, "/")
                    entries.append({"path": full_path, "key": key, "filename": filename})
    else:
        for filename in os.listdir(target_folder):
            if filename.lower().endswith(".pdf"):
                entries.append({
                    "path": os.path.join(target_folder, filename),
                    "key": filename,
                    "filename": filename,
                })

    if not entries:
        print(f"⚠️ No PDF files found in: {target_folder}")

    return sorted(entries, key=lambda e: e["key"])

def process_single_file(file_path: str, filename: str, idx: int, total: int) -> Dict:
    """
    Process a single PDF file.
    
    Args:
        file_path: Full path to PDF file
        filename: Name of the file
        idx: Current file index (for progress display)
        total: Total number of files
    
    Returns:
        Dictionary with extracted data
    """
    file_id = filename.replace(".pdf", "")
    print(f"\n{'='*80}")
    print(f"📄 [{idx}/{total}] Processing: {filename}")
    print(f"{'='*80}")
    
    file_data = {"ID": file_id}
    
    try:
        # Extract metadata
        print(f"\n📋 Extracting monograph metadata...")
        metadata = extract_metadata(file_path, filename)
        file_data.update(metadata)
        print(f"  ✅ Brand: {metadata['Brand Name']}")
        print(f"     Company: {metadata['Company']}")
        
        # Extract indications
        print(f"\n💊 Extracting indications...")
        file_data["Indications"] = extract_indications_from_pdf(file_path, filename)
        
        print(f"\n🚫 Extracting contraindications...")
        file_data["Contraindications"] = extract_contraindications_from_pdf(file_path, filename)

        # Extract serious warnings
        print(f"\n⚠️ Extracting serious warnings...")
        file_data["Serious Warnings"] = extract_warnings_from_pdf(file_path, filename)
        
        # Extract adverse events
        print(f"\n⚠️ Extracting adverse events...")
        file_data["Adverse Events"] = extract_adverse_events(file_path, filename)
        
        # Extract drug interactions
        print(f"\n💊 Extracting drug interactions...")
        file_data["Drug Interactions"] = extract_drug_interactions_from_pdf(file_path, filename)

        # Extract liver dose adjustment
        print(f"\n💊 Extracting liver dose adjustment...")
        file_data["Liver Dose Adjustment"] = extract_liver_dose_adjustment_from_pdf(file_path, filename)
        
        # Extract kidney dose adjustment
        print(f"\n💊 Extracting kidney dose adjustment...")
        file_data["Kidney Dose Adjustment"] = extract_kidney_dose_adjustment_from_pdf(file_path, filename)

        # Extract pharmacokinetics summary
        print(f"\n📊 Extracting pharmacokinetics summary...")
        file_data["Pharmacokinetics"] = extract_pharmacokinetics_from_pdf(file_path, filename)

        # Extract metabolism information
        print(f"\n🧬 Extracting metabolism (CYP enzymes)...")
        file_data["Metabolism"] = extract_metabolism_from_pdf(file_path, filename)

        # Extract elimination information
        print(f"\n🧪 Extracting elimination information...")
        file_data["Elimination"] = extract_elimination_from_pdf(file_path, filename)

        print(f"\n🔬 Extracting pharmacodynamics summary...")
        file_data["Pharmacodynamics"] = extract_pharmacodynamics_from_pdf(file_path, filename)

        # Extract pregnancy-related information
        print(f"\n🤰 Extracting pregnancy information...")
        pregnancy_data = extract_pregnancy_from_pdf(file_path, filename)
        file_data["Pregnancy Recommendation"] = pregnancy_data["Pregnancy Recommendation"]
        file_data["Pregnancy Summary"] = pregnancy_data["Pregnancy Summary"]

        print(f"\n🍼 Extracting breastfeeding information...")
        breastfeeding_data = extract_breastfeeding_from_pdf(file_path, filename)
        file_data["Breastfeeding Recommendation"] = breastfeeding_data["Breastfeeding Recommendation"]
        file_data["Breastfeeding Summary"] = breastfeeding_data["Breastfeeding Summary"]

        print(f"\n  ✅ COMPLETED: {filename}")
        
    except Exception as e:
        print(f"  ❌ Error processing {filename}: {e}")
        import traceback
        traceback.print_exc()
        # Add error data with all expected fields
        file_data.update({
            "Brand Name": f"ERROR: {str(e)}",
            "Company": f"ERROR: {str(e)}",
            "Initial Authorization": f"ERROR: {str(e)}",
            "Revision Date": f"ERROR: {str(e)}",
            "Ingredients": f"ERROR: {str(e)}",
            "Dosage": f"ERROR: {str(e)}",
            "Indications": f"ERROR: {str(e)}",
            "Contraindications": f"ERROR: {str(e)}",
            "Serious Warnings": f"ERROR: {str(e)}",
            "Adverse Events": f"ERROR: {str(e)}",
            "Drug Interactions": f"ERROR: {str(e)}",
            "Liver Dose Adjustment": f"ERROR: {str(e)}",
            "Kidney Dose Adjustment": f"ERROR: {str(e)}",
            "Pharmacokinetics Summary": f"ERROR: {str(e)}",
            "Metabolism": f"ERROR: {str(e)}",
            "Elimination": f"ERROR: {str(e)}",
            "Pharmacodynamics Summary": f"ERROR: {str(e)}",
            "Pregnancy Recommendation": f"ERROR: {str(e)}",
            "Pregnancy Summary": f"ERROR: {str(e)}",
            "Breastfeeding Recommendation": f"ERROR: {str(e)}",
            "Breastfeeding Summary": f"ERROR: {str(e)}"
        })
    
    return file_data

def write_excel(records: List[Dict], output_path: str) -> None:
    """Write the current records to Excel, replacing any previous version."""
    if not records:
        return

    df = pd.DataFrame(records)

    # Keep the documented column order, then append the provenance columns a
    # recursive run needs -- ID alone doesn't say which class/generic folder a
    # monograph came from.
    available_columns = [col for col in OUTPUT_COLUMN_ORDER if col in df.columns]
    trailing = [c for c in ("Source Path", "Drug Folder", "Therapeutic Class") if c in df.columns]
    df = df[available_columns + trailing]

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    # Write to a temp file first: a crash mid-write would otherwise leave a
    # corrupt spreadsheet where the last good one used to be.
    tmp_path = output_path + ".tmp.xlsx"
    df.to_excel(tmp_path, index=False)
    os.replace(tmp_path, output_path)


def print_summary(records: List[Dict], output_path: str) -> None:
    """Print per-field extraction counts for the run so far."""
    if not records:
        print(f"\n⚠️ No data to save")
        return

    total = len(records)

    def ok(field, sentinels):
        return sum(1 for d in records if d.get(field, "") not in sentinels)

    MISSING = ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"]
    SUMMARY_MISSING = MISSING + ["SUMMARY_GENERATION_FAILED"]

    metadata_success = sum(1 for d in records if not str(d.get("Brand Name", "")).startswith("ERROR"))

    print(f"\n{'=' * 80}")
    print(f"💾 Saved {total} records to {output_path}")
    print(f"\n📊 SUMMARY:")
    print(f"  ✅ Metadata extracted: {metadata_success}/{total}")
    print(f"  ✅ Indications extracted: {ok('Indications', ['ERROR', 'NO_TEXT_FOUND', 'EXTRACTION_FAILED', '******'])}/{total}")
    print(f"  ✅ Contraindications extracted: {ok('Contraindications', MISSING)}/{total}")
    print(f"  ✅ Serious warnings extracted: {ok('Serious Warnings', ['ERROR', 'NO_TEXT_FOUND', 'EXTRACTION_FAILED', '******'])}/{total}")
    print(f"  ✅ Adverse events extracted: {ok('Adverse Events', ['ERROR', 'NO_TEXT_FOUND', 'CONTENT_EXTRACTION_FAILED', 'EXTRACTION_FAILED'])}/{total}")
    print(f"  ✅ Drug interactions extracted: {ok('Drug Interactions', MISSING + ['******'])}/{total}")
    print(f"  ✅ Liver dose adjustment extracted: {ok('Liver Dose Adjustment', MISSING)}/{total}")
    print(f"  ✅ Kidney dose adjustment extracted: {ok('Kidney Dose Adjustment', MISSING)}/{total}")
    print(f"  ✅ Pharmacokinetics summary extracted: {ok('Pharmacokinetics', SUMMARY_MISSING)}/{total}")
    print(f"  ✅ Metabolism (CYP enzymes): {ok('Metabolism', MISSING)}/{total}")
    print(f"  ✅ Elimination (urine/faeces): {ok('Elimination', MISSING)}/{total}")
    print(f"  ✅ Pharmacodynamics summary extracted: {ok('Pharmacodynamics', SUMMARY_MISSING)}/{total}")
    print(f"  ✅ Pregnancy information extracted: {ok('Pregnancy Recommendation', MISSING)}/{total}")
    print(f"  ✅ Breastfeeding information extracted: {ok('Breastfeeding Recommendation', MISSING)}/{total}")
    print(f"{'=' * 80}")


def save_results(folder_dataset: List[Dict], folder_name: str, output_dir: str = ".") -> str:
    """Write the Excel output and print the run summary. Returns the path."""
    output_path = os.path.join(output_dir, f"{folder_name}_complete_extraction.xlsx")
    write_excel(folder_dataset, output_path)
    print_summary(folder_dataset, output_path)
    return output_path


def _provenance(entry: Dict) -> Dict:
    """Class and generic folder names recovered from the file's path."""
    parts = entry["key"].split("/")
    return {
        "Source Path": entry["key"],
        "Drug Folder": parts[-2] if len(parts) >= 2 else "",
        "Therapeutic Class": parts[-3] if len(parts) >= 3 else "",
    }


def run_pipeline(
    target_folder: str,
    output_dir: str = ".",
    recursive: bool = True,
    resume: bool = True,
    retry_failed: bool = False,
    limit: int = None,
) -> None:
    """
    Run the complete extraction pipeline.

    Every finished record is appended to a JSONL checkpoint before the next PDF
    starts, so an interrupted multi-day run resumes where it stopped instead of
    losing everything. The Excel is rebuilt from that checkpoint periodically
    and at the end.

    Args:
        target_folder: Root folder containing monograph PDFs
        output_dir: Where the Excel and checkpoint are written
        recursive: Walk subfolders (the corpus is class/generic nested)
        resume: Skip PDFs already present in the checkpoint
        retry_failed: Also re-process checkpointed records that errored out
        limit: Stop after this many newly processed files (for a smoke test)
    """
    entries = get_pdf_files(target_folder, recursive=recursive)
    if not entries:
        return

    folder_name = os.path.basename(os.path.normpath(target_folder))
    os.makedirs(output_dir, exist_ok=True)
    checkpoint_path = os.path.join(output_dir, f"{folder_name}_checkpoint.jsonl")
    output_path = os.path.join(output_dir, f"{folder_name}_complete_extraction.xlsx")

    records = load_records(checkpoint_path) if resume else []
    done = completed_keys(records)

    if retry_failed and records:
        retryable = failed_keys(records)
        if retryable:
            records = [r for r in records if r.get("Source Path") not in retryable]
            rewrite_records(checkpoint_path, records)
            done -= retryable
            print(f"♻️ Retrying {len(retryable)} previously failed file(s)")

    pending = [e for e in entries if e["key"] not in done]
    if limit is not None:
        pending = pending[:limit]

    print(f"📂 Processing: {target_folder}")
    print(f"🔧 Extracting: All features")
    print(f"📄 {len(entries)} PDF(s) found | {len(done)} already done | {len(pending)} to process")
    print(f"🧷 Checkpoint: {checkpoint_path}")

    if not pending:
        print("✅ Nothing left to process.")
        if records:
            write_excel(records, output_path)
            print_summary(records, output_path)
        return

    run_started = time.time()

    for idx, entry in enumerate(pending, 1):
        start_time = time.time()

        file_data = process_single_file(entry["path"], entry["filename"], idx, len(pending))
        file_data.update(_provenance(entry))

        # Checkpoint before anything else gets a chance to fail.
        append_record(checkpoint_path, file_data)
        records.append(file_data)

        if idx % EXCEL_FLUSH_EVERY == 0:
            write_excel(records, output_path)

        avg = (time.time() - run_started) / idx
        remaining = avg * (len(pending) - idx)
        print(f"  ⏱️ {idx}/{len(pending)} done | avg {avg:.1f}s/file | ~{remaining / 3600:.1f}h remaining")

        # Rate limiting
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    write_excel(records, output_path)
    print_summary(records, output_path)
