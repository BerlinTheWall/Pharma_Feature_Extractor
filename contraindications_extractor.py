"""Extract contraindications from pharmaceutical monographs using TOC page detection."""

import os
import time
import re
import pandas as pd
from .notify import beep
from .config import SAFE_DELAY, CONTRAINDICATIONS_OUTPUT_FOLDER, MAX_SECTION_CHARS
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api, call_ai_api_keywords
from .prompts import CONTRAINDICATIONS_EXTRACTION_PROMPT, CONTRAINDICATIONS_SYSTEM_MESSAGE

def create_flexible_pattern(text):
    """Create a flexible pattern that matches text with possible spaces."""
    words = text.split()
    pattern_parts = []
    
    for word in words:
        if len(word) > 3:
            word_pattern = ''
            for i, char in enumerate(word):
                word_pattern += char
                if i < len(word) - 1:
                    word_pattern += r'\s*'
            pattern_parts.append(word_pattern)
        else:
            pattern_parts.append(word)
    
    return r'\s+'.join(pattern_parts)

def find_contraindications_section_pages(pages_text, filename):
    """
    Search the Table of Contents to find which pages contain the Contraindications section.
    """
    print(f"  🔍 Searching TOC for Contraindications section...")
    
    # Combine text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:8]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Variations of contraindications section names
    contraindications_variations = [
        'CONTRAINDICATIONS',
        'CONTRAINDICATIONS AND PRECAUTIONS',
        'ABSOLUTE CONTRAINDICATIONS',
        'RELATIVE CONTRAINDICATIONS'
    ]
    
    # Create flexible patterns
    flexible_patterns = []
    for variation in contraindications_variations:
        flexible_patterns.append(create_flexible_pattern(variation))
    
    # Look for section in TOC
    for pattern in flexible_patterns:
        # Pattern 1: "4.1 CONTRAINDICATIONS...........2"
        pattern1 = r'(\d+\.?\d*)\s+' + pattern + r'[^\d]*?\.{2,}\s*(\d+)'
        matches = re.finditer(pattern1, toc_text, re.IGNORECASE)
        for match in matches:
            section_num, page = match.groups()
            print(f"    ✅ Found in TOC: Section {section_num} on page {page}")
            return int(page), section_num
        
        # Pattern 2: "4.1 CONTRAINDICATIONS 2"
        pattern2 = r'(\d+\.?\d*)\s+' + pattern + r'[^\d]*?\s+(\d+)(?:\s|$)'
        matches = re.finditer(pattern2, toc_text, re.IGNORECASE)
        for match in matches:
            section_num, page = match.groups()
            print(f"    ✅ Found in TOC: Section {section_num} on page {page}")
            return int(page), section_num
        
        # Pattern 3: "CONTRAINDICATIONS...........2" (no section number)
        pattern3 = pattern + r'[^\d]*?\.{2,}\s*(\d+)'
        matches = re.finditer(pattern3, toc_text, re.IGNORECASE)
        for match in matches:
            page = match.group(1)
            print(f"    ✅ Found in TOC: Contraindications on page {page}")
            return int(page), None
    
    # If not found in TOC, search document for section header
    print(f"    Searching document for section header...")
    for page_data in pages_text:
        for variation in contraindications_variations:
            pattern = create_flexible_pattern(variation)
            lines = page_data['text'].split('\n')
            for line in lines[:5]:
                if re.search(r'^\s*' + pattern + r'\s*$', line, re.IGNORECASE):
                    print(f"    ✅ Found section header on page {page_data['page_num']}")
                    return page_data['page_num'], None
    
    return None, None

def find_next_section_page_contraindications(pages_text, start_page, current_section_num, filename):
    """Find where the next major section starts after Contraindications."""
    print(f"    🔍 Searching for next section (WARNINGS AND PRECAUTIONS)...")
    
    # Common next sections after Contraindications
    next_sections = [
        'SERIOUS WARNINGS AND PRECAUTIONS BOX',
        'WARNINGS AND PRECAUTIONS',
        'WARNINGS',
        'PRECAUTIONS',
        'DOSAGE AND ADMINISTRATION'
    ]
    
    flexible_patterns = [create_flexible_pattern(s) for s in next_sections]
    
    # Check TOC first
    toc_text = ""
    for page_data in pages_text[:10]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # If we have a section number, find next numbered section
    if current_section_num:
        try:
            current_num = float(current_section_num) if '.' in current_section_num else int(current_section_num)
            
            section_pattern = r'(\d+\.?\d*)\s+([A-Z][A-Z\s]+(?:[A-Z\s]*))[^\d]*?\.{2,}\s*(\d+)'
            next_section_page = None
            next_section_num = float('inf')
            
            for match in re.finditer(section_pattern, toc_text, re.IGNORECASE):
                section_num_str, section_name, page_str = match.groups()
                try:
                    section_num = float(section_num_str) if '.' in section_num_str else int(section_num_str)
                    page_num = int(page_str)
                    
                    if section_num > current_num and page_num > start_page:
                        if section_num < next_section_num:
                            next_section_num = section_num
                            next_section_page = page_num
                except ValueError:
                    continue
            
            if next_section_page:
                print(f"    ✅ Found next section on page {next_section_page}")
                return next_section_page
        except ValueError:
            pass
    
    # Search document for next section header
    for page_data in pages_text:
        if page_data['page_num'] > start_page:
            for pattern in flexible_patterns:
                lines = page_data['text'].split('\n')
                for line in lines[:3]:
                    if re.search(r'^\s*' + pattern + r'\s*$', line, re.IGNORECASE | re.MULTILINE):
                        print(f"    ✅ Found next section on page {page_data['page_num']}")
                        return page_data['page_num']
    
    # Default: limit to 4 pages (contraindications section is usually short)
    estimated_end = min(start_page + 4, len(pages_text))
    print(f"    ⚠️ Using default limit: page {estimated_end}")
    return estimated_end

def extract_contraindications_content(pages_text, start_page, end_page, filename):
    """Extract contraindications content from pages."""
    if not start_page:
        return None
    
    print(f"    📄 Extracting from page {start_page} to page {end_page}")
    contraindications_content = []
    
    for page_data in pages_text:
        page_num = page_data['page_num']
        
        if page_num < start_page:
            continue
        if page_num > end_page:
            break
        
        if page_num == start_page:
            lines = page_data['text'].split('\n')
            found_header = False
            page_content = []
            
            contraindications_headers = ['CONTRAINDICATIONS', 'CONTRAINDICATIONS AND PRECAUTIONS']
            for line in lines:
                if not found_header:
                    for header in contraindications_headers:
                        if re.search(create_flexible_pattern(header), line, re.IGNORECASE):
                            found_header = True
                            page_content.append(line)
                            break
                else:
                    page_content.append(line)
            
            if page_content:
                contraindications_content.append('\n'.join(page_content))
        else:
            contraindications_content.append(page_data['text'])
    
    if contraindications_content:
        return '\n'.join(contraindications_content)
    return None

def extract_contraindications_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Extract contraindications from a single PDF file using TOC page detection.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        Comma-separated list of contraindications or error message
    """
    try:
        # Extract ALL text from PDF with page numbers
        pages_text = extract_pdf_text(pdf_path, pages=None)
        
        if not pages_text:
            return "NO_TEXT_FOUND"
        
        if isinstance(pages_text, str):
            print(f"  ⚠️ Unexpected return type: got string instead of list")
            return "TEXT_EXTRACTION_ERROR"

        # Find Contraindications section using TOC
        start_page, section_num = find_contraindications_section_pages(pages_text, filename)
        
        if not start_page:
            print(f"  ⚠️ Could not find Contraindications section")
            return "SECTION_NOT_FOUND"
        
        # Find where the section ends
        end_page = find_next_section_page_contraindications(pages_text, start_page, section_num, filename)
        
        # Extract the contraindications content
        contraindications_section = extract_contraindications_content(pages_text, start_page, end_page, filename)
        
        if not contraindications_section:
            return "EXTRACTION_FAILED"
        
        # Use AI to extract clean contraindications
        prompt = CONTRAINDICATIONS_EXTRACTION_PROMPT.format(
            contraindications_text=contraindications_section[:MAX_SECTION_CHARS]
        )
        result = call_ai_api_keywords(
            prompt, CONTRAINDICATIONS_SYSTEM_MESSAGE, filename, "Contraindications",
            source_text=contraindications_section[:MAX_SECTION_CHARS], temperature=0.1
        )
        
        if result and result != "********":
            print(f"    ✅ Extracted contraindications: {result[:100]}..." if len(result) > 100 else f"    ✅ Extracted contraindications: {result}")
            return result
        
        return "********" if result == "********" else "EXTRACTION_FAILED"
        
    except Exception as e:
        print(f"    ❌ Error in extract_contraindications_from_pdf: {e}")
        import traceback
        traceback.print_exc()
        return f"ERROR: {str(e)}"

def process_contraindications_folder(target_folder):
    """Process all PDFs and extract contraindications using TOC page detection."""
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - CONTRAINDICATIONS EXTRACTION")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        contraindications = extract_contraindications_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Contraindications": contraindications
        })
        
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        print(f"     Contraindications: {contraindications[:200]}..." if len(contraindications) > 200 else f"     Contraindications: {contraindications}")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(CONTRAINDICATIONS_OUTPUT_FOLDER):
            os.makedirs(CONTRAINDICATIONS_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {CONTRAINDICATIONS_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(CONTRAINDICATIONS_OUTPUT_FOLDER, f"{folder_name}_contraindications.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print preview
        print(f"\n📊 SUMMARY PREVIEW:")
        for item in folder_dataset[:3]:
            contraindications = item['Contraindications']
            if len(contraindications) > 100:
                contraindications = contraindications[:100] + "..."
            print(f"  {item['ID']}: {contraindications}")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/ACE Inhibitor/Cilazapril"
    process_contraindications_folder(test_folder)
    
    try:
        beep()
    except:
        pass
    
    print("\n✨ Contraindications extraction complete!")