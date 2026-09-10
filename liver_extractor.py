"""Extract liver function dose adjustment information from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
from .notify import beep
from .config import client, SAFE_DELAY, LIVER_OUTPUT_FOLDER
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import LIVER_DOSE_EXTRACTION_PROMPT, LIVER_SYSTEM_MESSAGE

def find_dosage_section_pages(pages_text, filename):
    """
    Search the Table of Contents to find which pages contain the Dosage and Administration section.
    Returns tuple of (start_page, section_number) or (None, None) if not found.
    """
    
    print(f"  🔍 Searching TOC for Dosage and Administration section...")
    
    # Combine all text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:3]:  # Check first 3 pages for TOC
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Create variations of "DOSAGE AND ADMINISTRATION" that might appear
    dosage_variations = [
        r'DOSAGE\s+AND\s+ADMINISTRATION',
        r'DOSAGE\s+AND\s+ADMINISTR\s*ATION',
        r'DOSAGE\s+AND\s+ADMINISTRAT\s*ION',
        r'DOSAGE\s+AND\s+ADMIN\s*ISTRATION',
        r'DOSAGE\s+&?\s*ADMINISTRATION',
        r'DOSAGE\s+ADMINISTRATION',
    ]
    
    # Look for DOSAGE AND ADMINISTRATION in TOC format
    toc_patterns = []
    
    for dosage_var in dosage_variations:
        toc_patterns.append(r'(\d+\.?\d*)\s+' + dosage_var + r'[^\d]*?\.{2,}\s*(\d+)')
        toc_patterns.append(r'(\d+\.?\d*)\s+' + dosage_var + r'[^\d]*?\s+(\d+)(?:\s|$)')
        toc_patterns.append(dosage_var + r'[^\d]*?\.{2,}\s*(\d+)')
        toc_patterns.append(dosage_var + r'[^\d]*?\s+(\d+)(?:\s|$)')
    
    toc_patterns.append(r'(\d+)\s+\.{2,}\s+' + r'(?:DOSAGE\s+AND\s+ADMINISTRATION|DOSAGE\s+ADMINISTRATION)')
    
    for pattern in toc_patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                section_num, page = match.groups()
                print(f"    ✅ Found in TOC: Section {section_num} on page {page}")
                return int(page), section_num
            elif len(match.groups()) == 1:
                page = match.group(1)
                print(f"    ✅ Found in TOC: Dosage and Administration on page {page}")
                return int(page), None
    
    # Aggressive search
    print(f"    ⚠️ Not found with standard patterns, trying aggressive search...")
    lines = toc_text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'DOSAGE', line, re.IGNORECASE) and re.search(r'ADMINISTR', line, re.IGNORECASE):
            page_match = re.search(r'(\d+)\s*$', line)
            if page_match:
                page = page_match.group(1)
                print(f"    ✅ Found via aggressive search on page {page}")
                return int(page), None
            
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                page_match = re.search(r'^\s*(\d+)\s*$', next_line)
                if page_match:
                    page = page_match.group(1)
                    print(f"    ✅ Found via aggressive search (page on next line): {page}")
                    return int(page), None
    
    # Search document for section header
    print(f"    ⚠️ Not found in TOC, searching document for section header...")
    header_patterns = [
        r'DOSAGE\s+AND\s+ADMINISTRATION',
        r'DOSAGE\s+AND\s+ADMINISTR\s*ATION',
        r'DOSAGE\s+AND\s+ADMINISTRAT\s*ION',
        r'DOSAGE\s+&?\s*ADMINISTRATION',
        r'DOSAGE\s+ADMINISTRATION',
    ]
    
    for page_data in pages_text:
        for pattern in header_patterns:
            if re.search(pattern, page_data['text'], re.IGNORECASE):
                print(f"    ✅ Found section header on page {page_data['page_num']}")
                return page_data['page_num'], None
    
    return None, None

def find_next_section_page(pages_text, start_page, current_section_num, filename):
    """
    Find where the next major section starts after Dosage and Administration.
    Looks for OVERDOSAGE section in TOC or document.
    """
    
    print(f"    🔍 Searching for next section (OVERDOSAGE) after Dosage and Administration...")
    
    toc_text = ""
    for page_data in pages_text[:5]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    toc_patterns = [
        r'(\d+\.?\d*)\s+OVERDOSAGE[^\d]*?\.{2,}\s*(\d+)',
        r'(\d+\.?\d*)\s+OVERDOSAGE[^\d]*?\s+(\d+)(?:\s|$)',
        r'OVERDOSAGE[^\d]*?\.{2,}\s*(\d+)',
        r'OVERDOSAGE[^\d]*?\s+(\d+)(?:\s|$)',
    ]
    
    for pattern in toc_patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                section_num, page = match.groups()
                print(f"    ✅ Found OVERDOSAGE in TOC: Section {section_num} on page {page}")
                return int(page)
            elif len(match.groups()) == 1:
                page = match.group(1)
                print(f"    ✅ Found OVERDOSAGE in TOC on page {page}")
                return int(page)
    
    # Search document for OVERDOSAGE header
    for page_data in pages_text:
        if page_data['page_num'] > start_page:
            if re.search(r'OVERDOSAGE', page_data['text'], re.IGNORECASE):
                print(f"    ✅ Found OVERDOSAGE header on page {page_data['page_num']}")
                return page_data['page_num']
    
    # Fallback
    for page_data in pages_text:
        if page_data['page_num'] > start_page:
            if re.search(r'ACTION AND CLINICAL PHARMACOLOGY|STORAGE AND STABILITY|DOSAGE FORMS', 
                        page_data['text'], re.IGNORECASE):
                print(f"    ⚠️ OVERDOSAGE not found, found alternative section on page {page_data['page_num']}")
                return page_data['page_num']
    
    estimated_end = start_page + 5
    print(f"    ⚠️ Could not find next section, estimating end at page {estimated_end}")
    return estimated_end

def extract_dosage_content(pages_text, start_page, end_page, filename):
    """Extract content from the identified page range."""
    
    if not start_page:
        return None
    
    print(f"    📄 Extracting from page {start_page} to page {end_page}")
    dosage_content = []
    
    for page_data in pages_text:
        page_num = page_data['page_num']
        
        if page_num < start_page:
            continue
        if page_num > end_page:
            break
        
        page_header = f"\n--- PAGE {page_num} (Dosage and Administration Section) ---\n"
        
        if page_num == start_page:
            lines = page_data['text'].split('\n')
            found_header = False
            page_content = []
            
            for line in lines:
                if not found_header and re.search(r'DOSAGE\s+AND\s+ADMINISTRATION', line, re.IGNORECASE):
                    found_header = True
                    page_content.append(line)
                elif found_header:
                    page_content.append(line)
            
            if page_content:
                dosage_content.append(page_header + '\n'.join(page_content))
        else:
            dosage_content.append(page_header + page_data['text'])
    
    if dosage_content:
        total_chars = sum(len(content) for content in dosage_content)
        print(f"    📊 Extracted {len(dosage_content)} pages, {total_chars} characters")
        return '\n'.join(dosage_content)
    
    print(f"    ❌ No content extracted")
    return None

def extract_liver_dose_adjustment_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Extract dose adjustment information for liver function from a single PDF file.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        String with dose adjustment recommendation for liver
    """
    try:
        # Extract all text from PDF with page numbers
        pages_text = extract_pdf_text(pdf_path, pages=None)
        if not pages_text:
            return "NO_TEXT_FOUND"

        # Find Dosage and Administration section
        start_page, section_num = find_dosage_section_pages(pages_text, filename)
        
        if not start_page:
            return "SECTION_NOT_FOUND"
        
        # Find next section (OVERDOSAGE)
        end_page = find_next_section_page(pages_text, start_page, section_num, filename)
        
        # Extract content from Dosage section
        dosage_section = extract_dosage_content(pages_text, start_page, end_page, filename)
        
        if not dosage_section:
            return "EXTRACTION_FAILED"
        
        # Extract liver dose adjustment info
        prompt = LIVER_DOSE_EXTRACTION_PROMPT.format(dosage_section_text=dosage_section)
        result = call_ai_api(prompt, LIVER_SYSTEM_MESSAGE, filename, temperature=0.1)
        
        if result:
            # Clean up the response
            result = result.strip()
            
            # Validate that result matches one of our expected options
            valid_options = [
                "Use with caution in liver impairment",
                "No dose adjustment required for liver impairment",
                "Dose adjustment recommended with liver impairment",
                "Contraindicated in patients with liver impairment"
            ]
            
            for valid_option in valid_options:
                if valid_option.lower() in result.lower():
                    print(f"    ✅ Found: {valid_option}")
                    return valid_option
            
            # If no match, return as is but with note
            if result:
                print(f"    ⚠️ Unexpected response: {result}")
                return result
        
        return "EXTRACTION_FAILED"
        
    except Exception as e:
        print(f"    ❌ Error in extract_liver_dose_adjustment_from_pdf: {e}")
        return f"ERROR: {str(e)}"

def process_liver_folder(target_folder):
    """Process all PDFs and extract dose adjustment information for liver only."""
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - LIVER ONLY")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        liver_info = extract_liver_dose_adjustment_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Liver Function Dose Adjustment": liver_info
        })
        
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        print(f"     Liver: {liver_info}")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(LIVER_OUTPUT_FOLDER):
            os.makedirs(LIVER_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {LIVER_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(LIVER_OUTPUT_FOLDER, f"{folder_name}_liver_dose_adjustment.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print summary
        print(f"\n📊 SUMMARY - LIVER ONLY:")
        for item in folder_dataset:
            print(f"  {item['ID']}: {item['Liver Function Dose Adjustment']}")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/Urinary anti-infectives/Nitrofurantoin"
    process_liver_folder(test_folder)
    
    try:
        beep()
    except:
        pass
    
    print("\n✨ Liver dose adjustment extraction complete!")