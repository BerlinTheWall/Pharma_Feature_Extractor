"""Extract pharmacodynamics summaries from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
import winsound
from .config import client, SAFE_DELAY, PD_OUTPUT_FOLDER
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import PD_SUMMARY_PROMPT, PD_SYSTEM_MESSAGE

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

def find_pharmacodynamics_section_pages(pages_text, filename):
    """
    Search the Table of Contents to find which pages contain the Pharmacodynamics section.
    Usually under ACTION AND CLINICAL PHARMACOLOGY section.
    """
    print(f"  🔍 Searching TOC for Pharmacodynamics section...")
    
    # Combine text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:8]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Variations of pharmacodynamics/section names
    pd_variations = [
        'MECHANISM OF ACTION',
        'PHARMACODYNAMICS',
        'ACTION AND CLINICAL PHARMACOLOGY',
        'CLINICAL PHARMACOLOGY',
    ]
    
    # Create flexible patterns
    flexible_patterns = []
    for variation in pd_variations:
        flexible_patterns.append(create_flexible_pattern(variation))
    
    # Look for section in TOC
    toc_patterns = []
    for pattern in flexible_patterns:
        toc_patterns.append(r'(\d+\.?\d*)\s+' + pattern + r'[^\d]*?\.{2,}\s*(\d+)')
        toc_patterns.append(r'(\d+\.?\d*)\s+' + pattern + r'[^\d]*?\s+(\d+)(?:\s|$)')
        toc_patterns.append(pattern + r'[^\d]*?\.{2,}\s*(\d+)')
    
    for pattern in toc_patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                section_num, page = match.groups()
                print(f"    ✅ Found in TOC: Section {section_num} on page {page}")
                return int(page), section_num
            elif len(match.groups()) == 1:
                page = match.group(1)
                print(f"    ✅ Found in TOC: Pharmacodynamics on page {page}")
                return int(page), None
    
    # If not found, search document for section header
    print(f"    Searching document for section header...")
    for page_data in pages_text:
        for variation in pd_variations:
            pattern = create_flexible_pattern(variation)
            if re.search(r'^\s*' + pattern + r'\s*$', page_data['text'], re.IGNORECASE | re.MULTILINE):
                print(f"    ✅ Found section header on page {page_data['page_num']}")
                return page_data['page_num'], None
    
    return None, None

def find_next_section_page(pages_text, start_page, current_section_num, filename):
    """Find where the next major section starts after Pharmacodynamics."""
    print(f"    🔍 Searching for next section...")
    
    # Common next sections (Pharmacokinetics or Special Populations)
    next_sections = [
        'PHARMACOKINETICS',
        'Pharmacokinetics',
        'Special Populations and Conditions',
        'Special Populations',
        'Congestive Heart Failure',
        'Heart Failure',
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
                if re.search(r'^\s*' + pattern + r'\s*$', page_data['text'], re.IGNORECASE | re.MULTILINE):
                    print(f"    ✅ Found next section on page {page_data['page_num']}")
                    return page_data['page_num']
    
    # Default limit
    estimated_end = min(start_page + 3, len(pages_text))
    print(f"    ⚠️ Using default limit: page {estimated_end}")
    return estimated_end

def extract_pd_content(pages_text, start_page, end_page, filename):
    """Extract pharmacodynamics content."""
    if not start_page:
        return None
    
    # Limit to 10 pages max
    if end_page - start_page + 1 > 10:
        end_page = start_page + 9
        print(f"    ⚠️ Limiting to 10 pages (up to page {end_page})")
    
    print(f"    📄 Extracting from page {start_page} to page {end_page}")
    pd_content = []
    
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
            
            pd_headers = ['MECHANISM OF ACTION', 'PHARMACODYNAMICS', 'ACTION AND CLINICAL PHARMACOLOGY', 'CLINICAL PHARMACOLOGY']
            for line in lines:
                if not found_header:
                    for header in pd_headers:
                        if re.search(create_flexible_pattern(header), line, re.IGNORECASE):
                            found_header = True
                            page_content.append(line)
                            break
                else:
                    page_content.append(line)
            
            if page_content:
                pd_content.append('\n'.join(page_content))
        else:
            pd_content.append(page_data['text'])
    
    if pd_content:
        return '\n'.join(pd_content)
    return None

def generate_pd_summary(pd_section_text, filename):
    """Generate a comprehensive paragraph summary of pharmacodynamics."""
    print(f"    📤 Sending {len(pd_section_text)} characters to API for PD summary")
    
    prompt = PD_SUMMARY_PROMPT.format(pd_section_text=pd_section_text)
    result = call_ai_api(prompt, PD_SYSTEM_MESSAGE, filename, temperature=0.2)
    
    if result:
        # Clean up any remaining formatting
        result = re.sub(r'^\s*[-•*]\s*', '', result)  # Remove bullet points
        result = re.sub(r'\n+', ' ', result)  # Replace newlines with spaces
        result = re.sub(r'\s+', ' ', result)  # Normalize whitespace
        result = re.sub(r'^["\']|["\']$', '', result)  # Remove quotes
        result = result.strip()
        
        if result:
            print(f"    ✅ Generated PD summary paragraph ({len(result)} chars)")
            return result
    
    return "SUMMARY_GENERATION_FAILED"

def extract_pharmacodynamics_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Extract pharmacodynamics summary from a single PDF file.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        Paragraph summary of pharmacodynamics or error message
    """
    try:
        # Extract all text from PDF with page numbers
        pages_text = extract_pdf_text(pdf_path, pages=None)
        if not pages_text:
            return "NO_TEXT_FOUND"

        # Find Pharmacodynamics section
        start_page, section_num = find_pharmacodynamics_section_pages(pages_text, filename)
        
        if not start_page:
            return "SECTION_NOT_FOUND"
        
        # Find next section
        end_page = find_next_section_page(pages_text, start_page, section_num, filename)
        
        # Extract content from Pharmacodynamics section
        pd_section = extract_pd_content(pages_text, start_page, end_page, filename)
        
        if not pd_section:
            return "EXTRACTION_FAILED"
        
        # Generate PD summary
        pd_summary = generate_pd_summary(pd_section, filename)
        
        if pd_summary == "SUMMARY_GENERATION_FAILED":
            return "SUMMARY_GENERATION_FAILED"
        
        return pd_summary
        
    except Exception as e:
        print(f"    ❌ Error in extract_pharmacodynamics_from_pdf: {e}")
        return f"ERROR: {str(e)}"

def process_pharmacodynamics_folder(target_folder):
    """Process all PDFs and extract pharmacodynamics summaries."""
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - PHARMACODYNAMICS")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        pd_summary = extract_pharmacodynamics_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Pharmacodynamics": pd_summary
        })
        
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        print(f"     PD Summary: {pd_summary[:200]}..." if len(pd_summary) > 200 else f"     PD Summary: {pd_summary}")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(PD_OUTPUT_FOLDER):
            os.makedirs(PD_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {PD_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(PD_OUTPUT_FOLDER, f"{folder_name}_pharmacodynamics.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print preview
        print(f"\n📊 SUMMARY PREVIEW:")
        for item in folder_dataset[:3]:
            summary = item['Pharmacodynamics']
            if len(summary) > 100:
                summary = summary[:100] + "..."
            print(f"  {item['ID']}: {summary}")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/Statin/Rosuvastatin"
    process_pharmacodynamics_folder(test_folder)
    
    try:
        winsound.Beep(440, 500)
    except:
        pass
    
    print("\n✨ Pharmacodynamics extraction complete!")