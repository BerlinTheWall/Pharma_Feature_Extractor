"""Main pipeline for processing pharmaceutical monographs."""

import os
import time
import pandas as pd
from typing import List, Dict

from .config import SAFE_DELAY, OUTPUT_COLUMN_ORDER
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


def get_pdf_files(target_folder: str) -> List[str]:
    """Get list of PDF files in target folder."""
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return []
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
    
    return all_files

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

def save_results(folder_dataset: List[Dict], folder_name: str) -> None:
    """Save extracted data to Excel file."""
    if not folder_dataset:
        print(f"\n⚠️ No data to save")
        return
    
    df = pd.DataFrame(folder_dataset)
    
    # Only keep columns that exist in the dataframe
    available_columns = [col for col in OUTPUT_COLUMN_ORDER if col in df.columns]
    df = df[available_columns]
    
    output_filename = f"{folder_name}_complete_extraction.xlsx"
    df.to_excel(output_filename, index=False)
    
    # Print summary
    metadata_success = sum(1 for d in folder_dataset if not str(d.get("Brand Name", "")).startswith("ERROR"))
    indications_success = sum(1 for d in folder_dataset if d.get("Indications", "") not in 
                             ["ERROR", "NO_TEXT_FOUND", "EXTRACTION_FAILED", "******"])
    contraindications_success = sum(1 for d in folder_dataset if d.get("Contraindications", "") not in 
                                ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])
    warnings_success = sum(1 for d in folder_dataset if d.get("Serious Warnings", "") not in 
                          ["ERROR", "NO_TEXT_FOUND", "EXTRACTION_FAILED", "******"])
    adverse_success = sum(1 for d in folder_dataset if d.get("Adverse Events", "") not in 
                         ["ERROR", "NO_TEXT_FOUND", "CONTENT_EXTRACTION_FAILED", "EXTRACTION_FAILED"])
    interactions_success = sum(1 for d in folder_dataset if d.get("Drug Interactions", "") not in
                              ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED", "******"])
    liver_success = sum(1 for d in folder_dataset if d.get("Liver Dose Adjustment", "") not in 
                    ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])
    kidney_success = sum(1 for d in folder_dataset if d.get("Kidney Dose Adjustment", "") not in 
                     ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])
    pk_success = sum(1 for d in folder_dataset if d.get("Pharmacokinetics Summary", "") not in 
                 ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED", "SUMMARY_GENERATION_FAILED"])
    metabolism_success = sum(1 for d in folder_dataset if d.get("Metabolism", "") not in 
                         ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])
    elimination_success = sum(1 for d in folder_dataset if d.get("Elimination", "") not in 
                         ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])
    pd_success = sum(1 for d in folder_dataset if d.get("Pharmacodynamics", "") not in 
                 ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED", "SUMMARY_GENERATION_FAILED"])
    pregnancy_success = sum(1 for d in folder_dataset if d.get("Pregnancy Recommendation", "") not in 
                        ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])
    breastfeeding_success = sum(1 for d in folder_dataset if d.get("Breastfeeding Recommendation", "") not in 
                        ["ERROR", "NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED"])

    print(f"\n{'='*80}")
    print(f"💾 Saved {len(folder_dataset)} records to {output_filename}")
    print(f"\n📊 SUMMARY:")
    print(f"  ✅ Metadata extracted: {metadata_success}/{len(folder_dataset)}")
    print(f"  ✅ Indications extracted: {indications_success}/{len(folder_dataset)}")
    print(f"  ✅ Contraindications extracted: {contraindications_success}/{len(folder_dataset)}")
    print(f"  ✅ Serious warnings extracted: {warnings_success}/{len(folder_dataset)}")
    print(f"  ✅ Adverse events extracted: {adverse_success}/{len(folder_dataset)}")
    print(f"  ✅ Drug interactions extracted: {interactions_success}/{len(folder_dataset)}")
    print(f"  ✅ Liver dose adjustment extracted: {liver_success}/{len(folder_dataset)}")
    print(f"  ✅ Kidney dose adjustment extracted: {kidney_success}/{len(folder_dataset)}")
    print(f"  ✅ Pharmacokinetics summary extracted: {pk_success}/{len(folder_dataset)}")
    print(f"  ✅ Metabolism (CYP enzymes): {metabolism_success}/{len(folder_dataset)}")
    print(f"  ✅ Elimination (urine/faeces): {elimination_success}/{len(folder_dataset)}")
    print(f"  ✅ Pharmacodynamics summary extracted: {pd_success}/{len(folder_dataset)}")
    print(f"  ✅ Breastfeeding information extracted: {breastfeeding_success}/{len(folder_dataset)}")
    print(f"{'='*80}")

def run_pipeline(target_folder: str) -> None:
    """
    Run the complete extraction pipeline.
    
    Args:
        target_folder: Path to folder containing PDF files
    """
    # Get PDF files
    files = get_pdf_files(target_folder)
    if not files:
        return
    
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(files)} files)")
    print(f"🔧 Extracting: All features")

    
    folder_dataset = []
    
    # Process each file
    for idx, filename in enumerate(files, 1):
        file_path = os.path.join(target_folder, filename)
        start_time = time.time()
        
        # Process file
        file_data = process_single_file(file_path, filename, idx, len(files))
        folder_dataset.append(file_data)
        
        # Rate limiting
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)
    
    # Save results
    save_results(folder_dataset, folder_name)