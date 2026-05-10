"""Extract breastfeeding information from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
import winsound
from .config import client, SAFE_DELAY, BREASTFEEDING_OUTPUT_FOLDER
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import BREASTFEEDING_SUMMARY_PROMPT, BREASTFEEDING_STATUS_PROMPT, BREASTFEEDING_SYSTEM_MESSAGE

def find_breastfeeding_section_pages(pages_text, filename):
    """
    Find pages containing breastfeeding information in WARNINGS AND PRECAUTIONS.
    Returns tuple of (start_page, end_page) or (None, None) if not found.
    """
    
    print(f"  🔍 Searching for breastfeeding section...")
    
    # First, search Table of Contents for breastfeeding-related entries
    toc_text = ""
    for page_data in pages_text[:5]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Patterns for breastfeeding in TOC
    breastfeeding_patterns = [
        r'Breast[- ]feeding[^\d]*\.{2,}\s*(\d+)',
        r'Nursing\s+Women[^\d]*\.{2,}\s*(\d+)',
        r'Lactation[^\d]*\.{2,}\s*(\d+)',
        r'7\.\d+\.?\d*\s+Breast[- ]feeding[^\d]*\.{2,}\s*(\d+)',
        r'Special\s+Populations[^\d]*\.{2,}\s*(\d+)',
        r'7\.1\s+Special\s+Populations[^\d]*\.{2,}\s*(\d+)',
        r'Breastfeeding\s+-\s+Risk\s+Summary[^\d]*\.{2,}\s*(\d+)',
    ]
    
    breastfeeding_page = None
    special_pop_page = None
    
    for pattern in breastfeeding_patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) >= 1:
                page_num = int(match.group(1))
                if 'Breast' in pattern or 'Nursing' in pattern or 'Lactation' in pattern:
                    breastfeeding_page = page_num
                    print(f"    ✅ Found 'Breastfeeding' in TOC on page {breastfeeding_page}")
                elif 'Special' in pattern:
                    special_pop_page = page_num
                    print(f"    ✅ Found 'Special Populations' in TOC on page {special_pop_page}")
    
    # If we found the breastfeeding section directly
    if breastfeeding_page:
        # Find where the next subsection starts
        end_page = find_next_subsection(pages_text, breastfeeding_page, 
                                       ['Pregnancy', 'Pregnant', 'Pediatrics', 'Geriatrics', 
                                        '7.1.2', '7.1.3', '7.2', '8 ADVERSE REACTIONS'])
        return breastfeeding_page, end_page
    
    # If we found Special Populations but not specific breastfeeding section
    if special_pop_page:
        print(f"    📍 Found Special Populations section, searching within...")
        # Search within Special Populations pages for breastfeeding content
        for page_data in pages_text:
            if page_data['page_num'] >= special_pop_page:
                if re.search(r'Breast[- ]feeding|Nursing|Lactation', page_data['text'], re.IGNORECASE):
                    print(f"    ✅ Found breastfeeding subsection on page {page_data['page_num']}")
                    end_page = find_next_subsection(pages_text, page_data['page_num'],
                                                   ['Pregnancy', 'Pregnant', 'Pediatrics', 'Geriatrics',
                                                    '7.1.2', '7.1.3'])
                    return page_data['page_num'], end_page
    
    # If not found in TOC, search through all pages for breastfeeding headers
    print(f"    🔍 Searching document for breastfeeding section headers...")
    
    header_patterns = [
        r'7\.1\.2\s+Breast[- ]feeding\s+Women',
        r'7\.1\.2\s+Nursing\s+Women',
        r'7\.1\.2\s+Lactation',
        r'Breast[- ]feeding\s+Women',
        r'Nursing\s+Women',
        r'Lactation\s+-\s+',
        r'Use in Breastfeeding',
        r'Pregnancy and Lactation',
        r'Breastfeeding\s+-\s+Risk\s+Summary',
    ]
    
    for page_data in pages_text:
        for pattern in header_patterns:
            if re.search(pattern, page_data['text'], re.IGNORECASE):
                print(f"    ✅ Found breastfeeding section header on page {page_data['page_num']}")
                end_page = find_next_subsection(pages_text, page_data['page_num'],
                                               ['Pregnancy', 'Pregnant', 'Pediatrics', 'Geriatrics',
                                                '7.1.1', '7.1.3', '7.2', '8 ADVERSE REACTIONS'])
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

def extract_breastfeeding_content(pages_text, start_page, end_page, filename):
    """
    Extract content from the identified page range.
    """
    if not start_page:
        return None
    
    print(f"    📄 Extracting breastfeeding content from page {start_page} to page {end_page}")
    
    breastfeeding_content = []
    
    for page_data in pages_text:
        page_num = page_data['page_num']
        
        if page_num < start_page:
            continue
        if page_num > end_page:
            break
        
        page_header = f"\n--- PAGE {page_num} (Breastfeeding Section) ---\n"
        
        if page_num == start_page:
            # On the start page, begin from the breastfeeding header
            lines = page_data['text'].split('\n')
            found_header = False
            page_content = []
            
            for line in lines:
                if not found_header and re.search(r'Breast[- ]feeding|Nursing|Lactation', line, re.IGNORECASE):
                    found_header = True
                    page_content.append(line)
                elif found_header:
                    page_content.append(line)
            
            if page_content:
                breastfeeding_content.append(page_header + '\n'.join(page_content))
        else:
            breastfeeding_content.append(page_header + page_data['text'])
    
    if breastfeeding_content:
        total_chars = sum(len(content) for content in breastfeeding_content)
        print(f"    📊 Extracted {len(breastfeeding_content)} pages, {total_chars} characters")
        return '\n'.join(breastfeeding_content)
    
    print(f"    ❌ No content extracted")
    return None

def extract_breastfeeding_status(breastfeeding_text, filename):
    """
    Extract the basic breastfeeding recommendation status.
    """
    prompt = BREASTFEEDING_STATUS_PROMPT.format(breastfeeding_text=breastfeeding_text[:20000])
    result = call_ai_api(prompt, "You output only one of: CONTRANDICATED, NOT RECOMMENDED, USE WITH CAUTION, CONSIDERED SAFE, NO INFORMATION", 
                         filename, temperature=0.1)
    
    if result:
        status = result.strip().upper()
        valid_statuses = ["CONTRANDICATED", "NOT RECOMMENDED", "USE WITH CAUTION", "CONSIDERED SAFE", "NO INFORMATION"]
        
        for valid in valid_statuses:
            if valid in status:
                return valid
        
        return "NO INFORMATION"
    
    return "NO INFORMATION"

def summarize_breastfeeding_information(breastfeeding_text, filename):
    """
    Generate a short summary of breastfeeding-related information.
    """
    print(f"    📤 Sending {len(breastfeeding_text)} characters to API for breastfeeding summary")
    
    prompt = BREASTFEEDING_SUMMARY_PROMPT.format(breastfeeding_text=breastfeeding_text[:5000])
    result = call_ai_api(prompt, BREASTFEEDING_SYSTEM_MESSAGE, filename, temperature=0.3)
    
    if result:
        print(f"    ✅ Generated summary ({len(result)} characters)")
        return result
    
    return "Breastfeeding information could not be extracted from this document."

def extract_breastfeeding_from_pdf(pdf_path: str, filename: str) -> dict:
    """
    Extract breastfeeding information from a single PDF file.
    
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
                "Breastfeeding Recommendation": "NO_TEXT_FOUND",
                "Breastfeeding Summary": "No text could be extracted from this PDF."
            }

        # Find pages containing breastfeeding information
        start_page, end_page = find_breastfeeding_section_pages(pages_text, filename)
        
        if not start_page:
            print(f"  ⚠️ Could not find breastfeeding section")
            return {
                "Breastfeeding Recommendation": "SECTION_NOT_FOUND",
                "Breastfeeding Summary": "No breastfeeding information found."
            }
        
        # Extract content from breastfeeding section
        breastfeeding_section = extract_breastfeeding_content(pages_text, start_page, end_page, filename)
        
        if not breastfeeding_section:
            print(f"  ⚠️ Could not extract breastfeeding content")
            return {
                "Breastfeeding Recommendation": "EXTRACTION_FAILED",
                "Breastfeeding Summary": "Breastfeeding section was identified but content could not be extracted."
            }
        
        # Extract breastfeeding status and generate summary
        breastfeeding_status = extract_breastfeeding_status(breastfeeding_section, filename)
        breastfeeding_summary = summarize_breastfeeding_information(breastfeeding_section, filename)
        
        return {
            "Breastfeeding Recommendation": breastfeeding_status,
            "Breastfeeding Summary": breastfeeding_summary
        }
        
    except Exception as e:
        print(f"    ❌ Error in extract_breastfeeding_from_pdf: {e}")
        return {
            "Breastfeeding Recommendation": f"ERROR: {str(e)[:100]}",
            "Breastfeeding Summary": f"An error occurred while processing this file: {str(e)}"
        }

def process_breastfeeding_folder(target_folder):
    """Process all PDFs and extract breastfeeding information with summaries."""
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - BREASTFEEDING INFORMATION")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        # Extract breastfeeding information
        breastfeeding_data = extract_breastfeeding_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Breastfeeding Recommendation": breastfeeding_data["Breastfeeding Recommendation"],
            "Breastfeeding Summary": breastfeeding_data["Breastfeeding Summary"]
        })
        
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        print(f"     Status: {breastfeeding_data['Breastfeeding Recommendation']}")
        print(f"     Summary: {breastfeeding_data['Breastfeeding Summary'][:150]}...")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(BREASTFEEDING_OUTPUT_FOLDER):
            os.makedirs(BREASTFEEDING_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {BREASTFEEDING_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(BREASTFEEDING_OUTPUT_FOLDER, f"{folder_name}_breastfeeding.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print summary
        print(f"\n📊 SUMMARY - BREASTFEEDING INFORMATION:")
        for item in folder_dataset:
            print(f"  {item['ID']}: {item['Breastfeeding Recommendation']}")
            print(f"     Summary: {item['Breastfeeding Summary'][:100]}...")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/Urinary anti-infectives/Nitrofurantoin"
    process_breastfeeding_folder(test_folder)
    
    try:
        winsound.Beep(440, 500)
    except:
        pass
    
    print("\n✨ Breastfeeding information extraction complete!")