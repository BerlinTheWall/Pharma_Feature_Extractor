"""Extract serious warnings and precautions from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
from .notify import beep
from .config import SAFE_DELAY, WARNINGS_PAGES
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import WARNINGS_EXTRACTION_PROMPT, WARNINGS_SYSTEM_MESSAGE

WARNINGS_OUTPUT_FOLDER = "warnings_precautions"


def extract_warnings_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Extract serious warnings and precautions from a single PDF file.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        Comma-separated list of warning topics or error message
    """
    try:
        # Extract text from specified pages (configurable in config.py)
        pdf_text = extract_pdf_text(pdf_path, pages=WARNINGS_PAGES)
        
        if not pdf_text:
            return "NO_TEXT_FOUND"
        
        # Call AI to extract warnings (using original prompt exactly as provided)
        prompt = WARNINGS_EXTRACTION_PROMPT.format(pdf_text=pdf_text[:15000])
        result = call_ai_api(prompt, WARNINGS_SYSTEM_MESSAGE, filename, temperature=0.1)
        
        if result:
            # Clean up the response
            result = result.strip()
            result = re.sub(r'\s+', ' ', result)
            result = re.sub(r',\s*', ', ', result)
            result = re.sub(r',\s*$', '', result)
            
            # Check if no warnings found
            if result == "********" or result == "":
                return "******"
            
            print(f"    ✅ Extracted warnings: {result[:100]}..." if len(result) > 100 else f"    ✅ Extracted warnings: {result}")
            return result
        
        return "EXTRACTION_FAILED"
        
    except Exception as e:
        print(f"    ❌ Error in extract_warnings_from_pdf: {e}")
        return f"ERROR: {str(e)}"

def process_warnings_folder(target_folder):
    """
    Process all PDFs in a folder and extract warnings and precautions.
    Saves results to a separate Excel file in the warnings folder.
    """
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - WARNINGS & PRECAUTIONS")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        # Extract warnings
        warnings = extract_warnings_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Serious Warnings": warnings
        })
        
        # Print result
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        if warnings and warnings not in ["NO_TEXT_FOUND", "EXTRACTION_FAILED", "ERROR"]:
            if warnings == "******":
                print(f"     Status: No serious warnings found")
            else:
                warning_count = len(warnings.split(','))
                print(f"     Found {warning_count} warning topics")
                print(f"     Warnings: {warnings[:100]}..." if len(warnings) > 100 else f"     Warnings: {warnings}")
        else:
            print(f"     Status: {warnings}")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(WARNINGS_OUTPUT_FOLDER):
            os.makedirs(WARNINGS_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {WARNINGS_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(WARNINGS_OUTPUT_FOLDER, f"{folder_name}_warnings.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print summary
        print(f"\n📊 SUMMARY - SERIOUS WARNINGS:")
        success_count = sum(1 for item in folder_dataset if item['Serious Warnings'] not in 
                          ["NO_TEXT_FOUND", "EXTRACTION_FAILED", "ERROR"])
        no_warnings_count = sum(1 for item in folder_dataset if item['Serious Warnings'] == "******")
        
        print(f"  ✅ Successfully extracted: {success_count}/{len(folder_dataset)} files")
        print(f"  ℹ️  No warnings found: {no_warnings_count}/{len(folder_dataset)} files")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/ACE Inhibitor/Cilazapril"
    process_warnings_folder(test_folder)
    
    try:
        beep()
    except:
        pass
    
    print("\n✨ Warnings and Precautions extraction complete!")