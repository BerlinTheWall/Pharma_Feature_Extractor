"""Extract pharmacokinetics summaries from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
import winsound
from .config import client, SAFE_DELAY, PK_OUTPUT_FOLDER
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import PK_SUMMARY_PROMPT, PK_SYSTEM_MESSAGE

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

def find_pharmacokinetics_section_pages(pages_text, filename):
    """
    Search the Table of Contents to find which pages contain the Pharmacokinetics section.
    """
    print(f"  🔍 Searching TOC for Pharmacokinetics section...")
    
    # Combine text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:8]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Variations of pharmacokinetics section names
    pk_variations = [
        'PHARMACOKINETICS',
    ]
    
    # Create flexible patterns
    flexible_patterns = []
    for variation in pk_variations:
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
                print(f"    ✅ Found in TOC: Pharmacokinetics on page {page}")
                return int(page), None
    
    # If not found, search document for section header
    print(f"    Searching document for section header...")
    for page_data in pages_text:
        for variation in pk_variations:
            pattern = create_flexible_pattern(variation)
            if re.search(r'^\s*' + pattern + r'\s*$', page_data['text'], re.IGNORECASE | re.MULTILINE):
                print(f"    ✅ Found section header on page {page_data['page_num']}")
                return page_data['page_num'], None
    
    return None, None

def find_next_section_page(pages_text, start_page, current_section_num, filename):
    """Find where the next major section starts after Pharmacokinetics."""
    print(f"    🔍 Searching for next section...")
    
    # Common next sections
    next_sections = [
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
    estimated_end = min(start_page + 10, len(pages_text))
    print(f"    ⚠️ Using default limit: page {estimated_end}")
    return estimated_end

def extract_pk_content(pages_text, start_page, end_page, filename):
    """Extract pharmacokinetics content."""
    if not start_page:
        return None
    
    # Limit to 10 pages max
    if end_page - start_page + 1 > 10:
        end_page = start_page + 9
        print(f"    ⚠️ Limiting to 10 pages (up to page {end_page})")
    
    print(f"    📄 Extracting from page {start_page} to page {end_page}")
    pk_content = []
    
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
            
            pk_headers = ['PHARMACOKINETICS', 'CLINICAL PHARMACOLOGY']
            for line in lines:
                if not found_header:
                    for header in pk_headers:
                        if re.search(create_flexible_pattern(header), line, re.IGNORECASE):
                            found_header = True
                            page_content.append(line)
                            break
                else:
                    page_content.append(line)
            
            if page_content:
                pk_content.append('\n'.join(page_content))
        else:
            pk_content.append(page_data['text'])
    
    if pk_content:
        return '\n'.join(pk_content)
    return None

def generate_pk_summary(pk_section_text, filename):
    """Generate a comprehensive paragraph summary of pharmacokinetics."""
    print(f"    📤 Sending {len(pk_section_text)} characters to API for PK summary")
    
    prompt = PK_SUMMARY_PROMPT.format(pk_section_text=pk_section_text)
    result = call_ai_api(prompt, PK_SYSTEM_MESSAGE, filename, temperature=0.2)
    
    if result:
        # Clean up the response
        result = re.sub(r'^\s*[-•*]\s*', '', result)  # Remove bullet points
        result = re.sub(r'\n+', ' ', result)  # Replace newlines with spaces
        result = re.sub(r'\s+', ' ', result)  # Normalize whitespace
        result = re.sub(r'^["\']|["\']$', '', result)  # Remove quotes
        result = result.strip()
        
        if result:
            print(f"    ✅ Generated PK summary paragraph ({len(result)} chars)")
            return result
    
    return "SUMMARY_GENERATION_FAILED"

def extract_pharmacokinetics_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Extract pharmacokinetics summary from a single PDF file.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        Paragraph summary of pharmacokinetics or error message
    """
    try:
        # Extract all text from PDF with page numbers
        pages_text = extract_pdf_text(pdf_path, pages=None)
        if not pages_text:
            return "NO_TEXT_FOUND"

        # Find Pharmacokinetics section
        start_page, section_num = find_pharmacokinetics_section_pages(pages_text, filename)
        
        if not start_page:
            return "SECTION_NOT_FOUND"
        
        # Find next section
        end_page = find_next_section_page(pages_text, start_page, section_num, filename)
        
        # Extract content from Pharmacokinetics section
        pk_section = extract_pk_content(pages_text, start_page, end_page, filename)
        
        if not pk_section:
            return "EXTRACTION_FAILED"
        
        # Generate PK summary
        pk_summary = generate_pk_summary(pk_section, filename)
        
        if pk_summary == "SUMMARY_GENERATION_FAILED":
            return "SUMMARY_GENERATION_FAILED"
        
        return pk_summary
        
    except Exception as e:
        print(f"    ❌ Error in extract_pharmacokinetics_from_pdf: {e}")
        return f"ERROR: {str(e)}"

def process_pharmacokinetics_folder(target_folder):
    """Process all PDFs and extract pharmacokinetics summaries."""
    
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return
    
    all_files = [f for f in os.listdir(target_folder) if f.endswith(".pdf")]
    
    if not all_files:
        print(f"⚠️ No PDF files found in: {target_folder}")
        return
    
    folder_dataset = []
    folder_name = os.path.basename(target_folder)
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - PHARMACOKINETICS")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        pk_summary = extract_pharmacokinetics_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Pharmacokinetics Summary": pk_summary
        })
        
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        print(f"     PK Summary: {pk_summary[:200]}..." if len(pk_summary) > 200 else f"     PK Summary: {pk_summary}")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        if not os.path.exists(PK_OUTPUT_FOLDER):
            os.makedirs(PK_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {PK_OUTPUT_FOLDER}")

        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(PK_OUTPUT_FOLDER, f"{folder_name}_pharmacokinetics.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print preview
        print(f"\n📊 SUMMARY PREVIEW:")
        for item in folder_dataset[:3]:
            summary = item['Pharmacokinetics Summary']
            if len(summary) > 100:
                summary = summary[:100] + "..."
            print(f"  {item['ID']}: {summary}")

# For standalone execution
if __name__ == "__main__":
    test_folder = "../Received Monographs/Product monograph/Anticoagulant/Rivaroxaban"
    process_pharmacokinetics_folder(test_folder)
    
    try:
        winsound.Beep(440, 500)
    except:
        pass
    
    print("\n✨ Pharmacokinetics extraction complete!")