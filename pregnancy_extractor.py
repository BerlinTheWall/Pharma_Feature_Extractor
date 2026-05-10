"""Extract pregnancy information from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
import winsound
from .config import client, SAFE_DELAY, PREGNANCY_OUTPUT_FOLDER
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import PREGNANCY_SUMMARY_PROMPT, PREGNANCY_STATUS_PROMPT, PREGNANCY_SYSTEM_MESSAGE

def find_pregnancy_section_pages(pages_text, filename):
    """
    Find pages containing pregnancy information in WARNINGS AND PRECAUTIONS.
    Returns tuple of (start_page, end_page) or (None, None) if not found.
    """
    
    print(f"  🔍 Searching for pregnancy section...")
    
    # First, search Table of Contents for pregnancy-related entries
    toc_text = ""
    for page_data in pages_text[:5]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Patterns for pregnancy in TOC
    pregnancy_patterns = [
        r'Pregnant\s*Women[^\d]*\.{2,}\s*(\d+)',
        r'Pregnancy[^\d]*\.{2,}\s*(\d+)',
        r'7\.\d+\.?\d*\s+Pregnant\s+Women[^\d]*\.{2,}\s*(\d+)',
        r'Special\s+Populations[^\d]*\.{2,}\s*(\d+)',
        r'7\.1\s+Special\s+Populations[^\d]*\.{2,}\s*(\d+)',
    ]
    
    pregnancy_page = None
    special_pop_page = None
    
    for pattern in pregnancy_patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) >= 1:
                page_num = int(match.group(1))
                if 'Pregnant' in pattern or 'Pregnancy' in pattern:
                    pregnancy_page = page_num
                    print(f"    ✅ Found 'Pregnant Women' in TOC on page {pregnancy_page}")
                elif 'Special' in pattern:
                    special_pop_page = page_num
                    print(f"    ✅ Found 'Special Populations' in TOC on page {special_pop_page}")
    
    # If we found the pregnancy section directly
    if pregnancy_page:
        # Find where the next subsection starts
        end_page = find_next_subsection(pages_text, pregnancy_page, 
                                       ['Breast-feeding', 'Nursing', 'Pediatrics', 'Geriatrics', 
                                        '7.1.2', '7.1.3', '7.2', '8 ADVERSE REACTIONS'])
        return pregnancy_page, end_page
    
    # If we found Special Populations but not specific pregnancy section
    if special_pop_page:
        print(f"    📍 Found Special Populations section, searching within...")
        # Search within Special Populations pages for pregnancy content
        for page_data in pages_text:
            if page_data['page_num'] >= special_pop_page:
                if re.search(r'Pregnant\s+Women|Pregnancy', page_data['text'], re.IGNORECASE):
                    print(f"    ✅ Found pregnancy subsection on page {page_data['page_num']}")
                    end_page = find_next_subsection(pages_text, page_data['page_num'],
                                                   ['Breast-feeding', 'Nursing', 'Pediatrics', 'Geriatrics',
                                                    '7.1.2', '7.1.3'])
                    return page_data['page_num'], end_page
    
    # If not found in TOC, search through all pages for pregnancy headers
    print(f"    🔍 Searching document for pregnancy section headers...")
    
    header_patterns = [
        r'7\.1\.1\s+Pregnant\s+Women',
        r'Pregnant\s+Women',
        r'Pregnancy\s+-\s+',
        r'Use in Pregnancy',
        r'Pregnancy and Lactation',
    ]
    
    for page_data in pages_text:
        for pattern in header_patterns:
            if re.search(pattern, page_data['text'], re.IGNORECASE):
                print(f"    ✅ Found pregnancy section header on page {page_data['page_num']}")
                end_page = find_next_subsection(pages_text, page_data['page_num'],
                                               ['Breast-feeding', 'Nursing', 'Pediatrics', 'Geriatrics',
                                                '7.1.2', '7.1.3', '7.2', '8 ADVERSE REACTIONS'])
                return page_data['page_num'], end_page
    
    return None, None

def find_next_subsection(pages_text, start_page, stop_headers):
    """
    Find where the next subsection starts.
    """
    for page_data in pages_text:
        if page_data['page_num'] > start_page:
            text = page_data['text']
            for header in stop_headers:
                if re.search(header, text, re.IGNORECASE):
                    print(f"    📍 Next section found on page {page_data['page_num']}")
                    return page_data['page_num']
    
    # If no stop header found, go 2 pages forward
    estimated_end = start_page + 2
    print(f"    ⚠️ Could not find next section, estimating end at page {estimated_end}")
    return estimated_end

def extract_pregnancy_content(pages_text, start_page, end_page, filename):
    """
    Extract content from the identified page range.
    """
    if not start_page:
        return None
    
    print(f"    📄 Extracting pregnancy content from page {start_page} to page {end_page}")
    
    pregnancy_content = []
    
    for page_data in pages_text:
        page_num = page_data['page_num']
        
        if page_num < start_page:
            continue
        if page_num > end_page:
            break
        
        page_header = f"\n--- PAGE {page_num} (Pregnancy Section) ---\n"
        
        if page_num == start_page:
            # On the start page, begin from the pregnancy header
            lines = page_data['text'].split('\n')
            found_header = False
            page_content = []
            
            for line in lines:
                if not found_header and re.search(r'Pregnant\s+Women|Pregnancy', line, re.IGNORECASE):
                    found_header = True
                    page_content.append(line)
                elif found_header:
                    page_content.append(line)
            
            if page_content:
                pregnancy_content.append(page_header + '\n'.join(page_content))
        else:
            pregnancy_content.append(page_header + page_data['text'])
    
    if pregnancy_content:
        total_chars = sum(len(content) for content in pregnancy_content)
        print(f"    📊 Extracted {len(pregnancy_content)} pages, {total_chars} characters")
        return '\n'.join(pregnancy_content)
    
    print(f"    ❌ No content extracted")
    return None

def extract_pregnancy_status(pregnancy_text, filename):
    """
    Extract the basic pregnancy recommendation status.
    """
    prompt = PREGNANCY_STATUS_PROMPT.format(pregnancy_text=pregnancy_text[:20000])
    result = call_ai_api(prompt, "You output only one of: CONTRANDICATED, NOT RECOMMENDED, USE WITH CAUTION, NO INFORMATION", 
                         filename, temperature=0.1)
    
    if result:
        status = result.strip().upper()
        valid_statuses = ["CONTRANDICATED", "NOT RECOMMENDED", "USE WITH CAUTION", "NO INFORMATION"]
        
        for valid in valid_statuses:
            if valid in status:
                return valid
        
        return "NO INFORMATION"
    
    return "NO INFORMATION"

def summarize_pregnancy_information(pregnancy_text, filename):
    """
    Generate a short summary of pregnancy-related information.
    """
    print(f"    📤 Sending {len(pregnancy_text)} characters to API for pregnancy summary")
    
    prompt = PREGNANCY_SUMMARY_PROMPT.format(pregnancy_text=pregnancy_text[:5000])
    result = call_ai_api(prompt, PREGNANCY_SYSTEM_MESSAGE, filename, temperature=0.3)
    
    if result:
        print(f"    ✅ Generated summary ({len(result)} characters)")
        return result
    
    return "Pregnancy information could not be extracted from this document."

def extract_pregnancy_from_pdf(pdf_path: str, filename: str) -> dict:
    """
    Extract pregnancy information from a single PDF file.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        Dictionary with 'status' and 'summary' keys
    """
    try:
        # Extract all text from PDF with page numbers
        pages_text = extract_pdf_text(pdf_path, pages=None)
        if not pages_text:
            return {
                "Pregnancy Recommendation": "NO_TEXT_FOUND",
                "Pregnancy Summary": "No text could be extracted from this PDF."
            }

        # Find pages containing pregnancy information
        start_page, end_page = find_pregnancy_section_pages(pages_text, filename)
        
        if not start_page:
            print(f"  ⚠️ Could not find pregnancy section")
            return {
                "Pregnancy Recommendation": "SECTION_NOT_FOUND",
                "Pregnancy Summary": "No pregnancy information found."
            }
        
        # Extract content from pregnancy section
        pregnancy_section = extract_pregnancy_content(pages_text, start_page, end_page, filename)
        
        if not pregnancy_section:
            print(f"  ⚠️ Could not extract pregnancy content")
            return {
                "Pregnancy Recommendation": "EXTRACTION_FAILED",
                "Pregnancy Summary": "Pregnancy section was identified but content could not be extracted."
            }
        
        # Extract pregnancy status and generate summary
        pregnancy_status = extract_pregnancy_status(pregnancy_section, filename)
        pregnancy_summary = summarize_pregnancy_information(pregnancy_section, filename)
        
        return {
            "Pregnancy Recommendation": pregnancy_status,
            "Pregnancy Summary": pregnancy_summary
        }
        
    except Exception as e:
        print(f"    ❌ Error in extract_pregnancy_from_pdf: {e}")
        return {
            "Pregnancy Recommendation": f"ERROR: {str(e)[:100]}",
            "Pregnancy Summary": f"An error occurred while processing this file: {str(e)}"
        }

def process_pregnancy_folder(target_folder):
    """Process all PDFs and extract pregnancy information with summaries."""
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - PREGNANCY INFORMATION")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        # Extract pregnancy information
        pregnancy_data = extract_pregnancy_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Pregnancy Recommendation": pregnancy_data["Pregnancy Recommendation"],
            "Pregnancy Summary": pregnancy_data["Pregnancy Summary"]
        })
        
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        print(f"     Status: {pregnancy_data['Pregnancy Recommendation']}")
        print(f"     Summary: {pregnancy_data['Pregnancy Summary'][:150]}...")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(PREGNANCY_OUTPUT_FOLDER):
            os.makedirs(PREGNANCY_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {PREGNANCY_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(PREGNANCY_OUTPUT_FOLDER, f"{folder_name}_pregnancy.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print summary
        print(f"\n📊 SUMMARY - PREGNANCY INFORMATION:")
        for item in folder_dataset:
            print(f"  {item['ID']}: {item['Pregnancy Recommendation']}")
            print(f"     Summary: {item['Pregnancy Summary'][:100]}...")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/Calcium channel blocker/Amlodipine"
    process_pregnancy_folder(test_folder)
    
    try:
        winsound.Beep(440, 500)
    except:
        pass
    
    print("\n✨ Pregnancy information extraction complete!")