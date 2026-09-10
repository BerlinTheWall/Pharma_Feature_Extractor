"""Extract drug interactions from pharmaceutical monographs."""

import os
import time
import re
import pandas as pd
from .config import SAFE_DELAY
from .notify import beep
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import DRUG_INTERACTIONS_EXTRACTION_PROMPT, DRUG_INTERACTIONS_SYSTEM_MESSAGE

# Configuration
INTERACTIONS_OUTPUT_FOLDER = "drug_interactions"

def create_flexible_pattern(text):
    """
    Create a flexible pattern that matches text with possible spaces in the middle of words.
    Example: "DOSAGE AND ADMINISTRATION" will match "DOSAGE AND ADMINISTR ATION"
    """
    words = text.split()
    pattern_parts = []
    
    for word in words:
        if len(word) > 3:  # Only apply to longer words
            word_pattern = ''
            for i, char in enumerate(word):
                word_pattern += char
                if i < len(word) - 1:
                    # Allow optional space between characters
                    word_pattern += r'\s*'
            pattern_parts.append(word_pattern)
        else:
            pattern_parts.append(word)
    
    # Join words with flexible spacing
    return r'\s+'.join(pattern_parts)

def find_drug_interactions_section_pages(pages_text, filename):
    """
    Search the Table of Contents to find which pages contain the Drug Interactions section.
    Returns tuple of (start_page, section_number) or (None, None) if not found.
    """
    print(f"  🔍 Searching TOC for Drug Interactions section...")
    
    # Combine all text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:5]:  # Check first 5 pages for TOC
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # Create base variations of "DRUG INTERACTIONS" that might appear
    base_variations = [
        'DRUG INTERACTIONS',
        'DRUG INTERACTION',
        'DRUG-DRUG INTERACTIONS',
        'INTERACTIONS WITH DRUGS',
        'INTERACTIONS',
    ]
    
    # Create flexible patterns for each variation (handles broken text like "INTERACT IONS")
    drug_interactions_variations = []
    for variation in base_variations:
        # Create flexible pattern that handles spaces within words
        flexible_pattern = create_flexible_pattern(variation)
        drug_interactions_variations.append(flexible_pattern)
        
        # Also add the variation with possible hyphens
        if ' ' in variation:
            hyphen_var = variation.replace(' ', r'[\s\-]+')
            drug_interactions_variations.append(hyphen_var)
    
    # Also add common OCR error patterns
    ocr_variations = [
        r'DRUG\s*I\s*N\s*T\s*E\s*R\s*A\s*C\s*T\s*I\s*O\s*N\s*S?',  # Handles spaced out letters
        r'DRUG\s*[-–]\s*DRUG\s*I\s*N\s*T\s*E\s*R\s*A\s*C\s*T\s*I\s*O\s*N\s*S?',
    ]
    drug_interactions_variations.extend(ocr_variations)
    
    # Look for DRUG INTERACTIONS in TOC format with improved patterns
    toc_patterns = []
    
    # Generate patterns for each variation
    for interaction_var in drug_interactions_variations:
        # With section number and dots
        toc_patterns.append(r'(\d+\.?\d*)\s+' + interaction_var + r'[^\d]*?\.{2,}\s*(\d+)')
        # With section number, no dots
        toc_patterns.append(r'(\d+\.?\d*)\s+' + interaction_var + r'[^\d]*?\s+(\d+)(?:\s|$)')
        # Just the name and page number with dots
        toc_patterns.append(interaction_var + r'[^\d]*?\.{2,}\s*(\d+)')
        # Just the name and page number without dots
        toc_patterns.append(interaction_var + r'[^\d]*?\s+(\d+)(?:\s|$)')
    
    # Also add patterns that might have the page number before the section name
    toc_patterns.append(r'(\d+)\s+\.{2,}\s+' + r'(?:' + '|'.join(drug_interactions_variations) + r')')
    
    for pattern in toc_patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                section_num, page = match.groups()
                print(f"    ✅ Found in TOC: Section {section_num} on page {page}")
                return int(page), section_num
            elif len(match.groups()) == 1:
                page = match.group(1)
                print(f"    ✅ Found in TOC: Drug Interactions on page {page}")
                return int(page), None
    
    # If not found in TOC with standard patterns, try a more aggressive search
    print(f"    ⚠️ Not found with standard patterns, trying aggressive search...")
    
    # Look for any line that contains DRUG and INTERACTIONS (with flexible spacing)
    lines = toc_text.split('\n')
    for i, line in enumerate(lines):
        # Check for DRUG with flexible spacing
        drug_pattern = r'D\s*R\s*U\s*G'
        interactions_pattern = r'I\s*N\s*T\s*E\s*R\s*A\s*C\s*T\s*I\s*O\s*N\s*S?'
        
        if re.search(drug_pattern, line, re.IGNORECASE) and re.search(interactions_pattern, line, re.IGNORECASE):
            # Try to extract page number from this line or next line
            page_match = re.search(r'(\d+)\s*$', line)
            if page_match:
                page = page_match.group(1)
                print(f"    ✅ Found via aggressive search on page {page}")
                return int(page), None
            
            # Check next line for page number
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                page_match = re.search(r'^\s*(\d+)\s*$', next_line)
                if page_match:
                    page = page_match.group(1)
                    print(f"    ✅ Found via aggressive search (page on next line): {page}")
                    return int(page), None
    
    # If still not found, search through all pages for the section header
    print(f"    ⚠️ Not found in TOC, searching document for section header...")
    
    # Create flexible patterns for section header search
    header_patterns = []
    for variation in base_variations:
        header_patterns.append(create_flexible_pattern(variation))
    
    # Add common header formats
    header_patterns.extend([
        r'^\s*' + create_flexible_pattern('DRUG INTERACTIONS') + r'\s*$',
        r'^\s*' + create_flexible_pattern('INTERACTIONS') + r'\s*$',
    ])
    
    for page_data in pages_text:
        for pattern in header_patterns:
            if re.search(pattern, page_data['text'], re.IGNORECASE):
                print(f"    ✅ Found section header on page {page_data['page_num']}")
                return page_data['page_num'], None
    
    return None, None

def find_next_section_page(pages_text, start_page, current_section_num, filename):
    """
    Find where the next major section starts after Drug Interactions.
    Returns the page where the next section begins.
    """
    print(f"    🔍 Searching for next section after Drug Interactions...")
    
    # Common next sections that might appear after Drug Interactions
    next_sections = [
        # Clinical pharmacology variations
        'CLINICAL PHARMACOLOGY',
        'CLINICAL PHARMACOKINETICS',
        'PHARMACOLOGY',
        'PHARMACOKINETICS',
        'PHARMACODYNAMICS',
        'ACTION AND CLINICAL PHARMACOLOGY',
        'MECHANISM OF ACTION',
        
        # Dosage and administration variations
        'DOSAGE AND ADMINISTRATION',
        'DOSAGE & ADMINISTRATION',
        'DOSAGE',
        'DOSING AND ADMINISTRATION',
        'DOSING',
        'ADMINISTRATION',
        
        # Other common sections
        'ADVERSE REACTIONS',
        'CONTRAINDICATIONS',
        'WARNINGS AND PRECAUTIONS',
        'WARNINGS',
        'PRECAUTIONS',
        'CLINICAL STUDIES',
        'CLINICAL TRIALS',
        'STORAGE AND STABILITY',
        'OVERDOSAGE',
        'HOW SUPPLIED',
        'DOSAGE FORMS AND STRENGTHS',
        'SUPPLIED',
        'PRESENTATION',
        'PACKAGING'
    ]
    
    # Create flexible patterns for each next section
    flexible_next_sections = []
    for section in next_sections:
        flexible_next_sections.append(create_flexible_pattern(section))
    
    # Combine all text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:10]:  # Check first 10 pages for TOC
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    # First, try to find in TOC
    print(f"    Searching TOC for next section...")
    
    # If we have a section number, find ALL numbered sections after current
    if current_section_num:
        try:
            # Convert to float for comparison (handles both "9" and "9.5")
            current_num = float(current_section_num) if '.' in current_section_num else int(current_section_num)
            
            print(f"    Current section number: {current_num}")
            
            # Find all numbered sections in TOC
            section_pattern = r'(\d+\.?\d*)\s+([A-Z][A-Z\s]+(?:[A-Z\s]*))[^\d]*?\.{2,}\s*(\d+)'
            numbered_sections = []
            
            for match in re.finditer(section_pattern, toc_text, re.IGNORECASE | re.MULTILINE):
                section_num_str, section_name, page_str = match.groups()
                try:
                    # Handle both integer and decimal section numbers
                    if '.' in section_num_str:
                        section_num = float(section_num_str)
                    else:
                        section_num = int(section_num_str)
                    
                    page_num = int(page_str)
                    
                    # Only consider sections that start after our current page
                    if page_num > start_page:
                        numbered_sections.append({
                            'num': section_num,
                            'name': section_name.strip(),
                            'page': page_num,
                            'num_str': section_num_str
                        })
                except ValueError:
                    continue
            
            # Sort by section number
            numbered_sections.sort(key=lambda x: x['num'])
            
            # Find the NEXT section after current
            next_section = None
            for section in numbered_sections:
                if section['num'] > current_num:
                    next_section = section
                    break
            
            if next_section:
                print(f"    ✅ Found next numbered section {next_section['num_str']} - {next_section['name']} on page {next_section['page']}")
                return next_section['page']
            else:
                print(f"    No numbered sections found after {current_num}")
                
        except ValueError as e:
            print(f"    Error parsing section number {current_section_num}: {e}")
    
    # If no numbered section found, search TOC for specific section names
    print(f"    Searching TOC for specific section names...")
    for next_section, flexible_pattern in zip(next_sections, flexible_next_sections):
        toc_patterns = [
            r'(\d+\.?\d*)\s+' + flexible_pattern + r'[^\d]*?\.{2,}\s*(\d+)',
            r'(\d+\.?\d*)\s+' + flexible_pattern + r'[^\d]*?\s+(\d+)(?:\s|$)',
            r'' + flexible_pattern + r'[^\d]*?\.{2,}\s*(\d+)',
            r'' + flexible_pattern + r'[^\d]*?\s+(\d+)(?:\s|$)',
        ]
        
        for pattern in toc_patterns:
            matches = re.finditer(pattern, toc_text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if len(match.groups()) == 2:
                    section_num, page = match.groups()
                    if int(page) > start_page:
                        print(f"    ✅ Found next section {next_section} in TOC on page {page}")
                        return int(page)
                elif len(match.groups()) == 1:
                    page = match.group(1)
                    if int(page) > start_page:
                        print(f"    ✅ Found next section {next_section} in TOC on page {page}")
                        return int(page)
    
    # If not found in TOC, search through document pages
    print(f"    Searching document pages for next section header...")
    
    for page_data in pages_text:
        if page_data['page_num'] > start_page:
            page_text = page_data['text']
            
            # First, look for numbered headers (e.g., "10. DOSAGE AND ADMINISTRATION")
            numbered_header_pattern = r'^\s*(\d+\.?\d*)\s+([A-Z][A-Z\s]+(?:[A-Z\s]*))'
            numbered_match = re.search(numbered_header_pattern, page_text, re.IGNORECASE | re.MULTILINE)
            
            if numbered_match:
                section_num = numbered_match.group(1)
                section_name = numbered_match.group(2).strip()
                print(f"    ✅ Found numbered section {section_num}: {section_name} on page {page_data['page_num']}")
                
                # If we have a current section number, verify this is after it
                if current_section_num:
                    try:
                        current_num = float(current_section_num) if '.' in current_section_num else int(current_section_num)
                        found_num = float(section_num) if '.' in section_num else int(section_num)
                        
                        if found_num > current_num:
                            return page_data['page_num']
                    except ValueError:
                        return page_data['page_num']
                else:
                    return page_data['page_num']
            
            # If no numbered header, look for the specific sections we care about
            for next_section, flexible_pattern in zip(next_sections, flexible_next_sections):
                # Check if this section appears as a header
                header_patterns = [
                    r'^\s*' + flexible_pattern + r'\s*$',  # Entire line is the header
                    r'\n\s*' + flexible_pattern + r'\s*\n',  # Header on its own line
                    r'^\s*' + flexible_pattern + r'\s*\n',  # Header at start with newline after
                ]
                
                for header_pattern in header_patterns:
                    if re.search(header_pattern, page_text, re.IGNORECASE | re.MULTILINE):
                        print(f"    ✅ Found next section {next_section} header on page {page_data['page_num']}")
                        return page_data['page_num']
    
    # If all else fails, limit to 10 pages total
    estimated_end = start_page + 9
    print(f"    ⚠️ Could not find next section, limiting to 10 pages total (up to page {estimated_end})")
    return estimated_end

def extract_drug_interactions_content(pages_text, start_page, end_page, filename):
    """
    Extract content from the identified page range.
    If the range is more than 10 pages, only extract the first 10 pages.
    """
    if not start_page:
        return None
    
    # Enforce maximum of 10 pages total
    original_end_page = end_page
    if end_page - start_page + 1 > 10:
        end_page = start_page + 9
        print(f"    ⚠️ Range exceeds 10 pages ({original_end_page - start_page + 1} pages). Limiting to first 10 pages (up to page {end_page})")
    
    print(f"    📄 Extracting from page {start_page} to page {end_page}")
    interactions_content = []
    
    for page_data in pages_text:
        page_num = page_data['page_num']
        
        # Only process pages within our range
        if page_num < start_page:
            continue
        if page_num > end_page:
            break
        
        # Add page marker
        page_header = f"\n--- PAGE {page_num} (Drug Interactions Section) ---\n"
        
        if page_num == start_page:
            # On the start page, begin from the section header
            lines = page_data['text'].split('\n')
            found_header = False
            page_content = []
            
            # Create flexible pattern for the header
            header_pattern = create_flexible_pattern('DRUG INTERACTIONS')
            
            for line in lines:
                if not found_header and re.search(header_pattern, line, re.IGNORECASE):
                    found_header = True
                    page_content.append(line)
                elif found_header:
                    page_content.append(line)
            
            if page_content:
                interactions_content.append(page_header + '\n'.join(page_content))
        else:
            # For subsequent pages, include entire page
            interactions_content.append(page_header + page_data['text'])
    
    if interactions_content:
        total_chars = sum(len(content) for content in interactions_content)
        print(f"    📊 Extracted {len(interactions_content)} pages, {total_chars} characters")
        return '\n'.join(interactions_content)
    
    print(f"    ❌ No content extracted")
    return None

def extract_drug_names(interactions_section_text, filename):
    """
    Extract drug names from the Drug Interactions section.
    Returns a string containing comma-separated drug names.
    """
    print(f"    📤 Sending {len(interactions_section_text)} characters to API for drug name extraction")
    
    prompt = DRUG_INTERACTIONS_EXTRACTION_PROMPT.format(interactions_section_text=interactions_section_text)
    result = call_ai_api(prompt, DRUG_INTERACTIONS_SYSTEM_MESSAGE, filename, temperature=0.1)
    
    if result:
        # Clean up the response
        # Remove any markdown, quotes, bullet points, or numbering
        result = re.sub(r'^["\']|["\']$', '', result)
        result = re.sub(r'^\s*[-•*]\s*', '', result)
        result = re.sub(r'^\d+\.\s*', '', result)
        
        # Remove any "and" that might appear
        result = re.sub(r'\s+and\s+', ', ', result, flags=re.IGNORECASE)
        
        # Ensure consistent spacing after commas
        result = re.sub(r'\s*,\s*', ', ', result)
        
        # Remove any trailing commas
        result = re.sub(r',\s*$', '', result)
        
        print(f"    ✅ Extracted drug names: {result[:100]}..." if len(result) > 100 else f"    ✅ Extracted drug names: {result}")
        return result
    
    return "EXTRACTION_FAILED"

def extract_drug_interactions_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Extract drug interactions from a single PDF file.
    This function is designed to be called from the main pipeline.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of the file (for logging)
    
    Returns:
        Comma-separated list of drug names or error message
    """
    try:
        # Extract all text from PDF with page numbers
        pages_text = extract_pdf_text(pdf_path, pages=None)
        if not pages_text:
            return "NO_TEXT_FOUND"

        # Find Drug Interactions section
        start_page, section_num = find_drug_interactions_section_pages(pages_text, filename)
        
        if not start_page:
            return "SECTION_NOT_FOUND"
        
        # Find next section
        end_page = find_next_section_page(pages_text, start_page, section_num, filename)
        
        # Extract content from Drug Interactions section
        interactions_section = extract_drug_interactions_content(pages_text, start_page, end_page, filename)
        
        if not interactions_section:
            return "EXTRACTION_FAILED"
        
        # Extract drug names using AI
        drug_names = extract_drug_names(interactions_section, filename)
        
        if not drug_names or drug_names == "EXTRACTION_FAILED":
            return "EXTRACTION_FAILED"
        
        # Return ****** if no drugs found (per the API prompt specification)
        if drug_names == "******":
            return "******"
        
        return drug_names
        
    except Exception as e:
        print(f"    ❌ Error in extract_drug_interactions_from_pdf: {e}")
        import traceback
        traceback.print_exc()
        return f"ERROR: {str(e)}"

def process_drug_interactions_folder(target_folder):
    """
    Process all PDFs in a folder and extract drug interaction information.
    This function saves results to a separate Excel file in the drug_interactions folder.
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
    print(f"📂 Processing Folder: {folder_name} ({len(all_files)} files) - DRUG INTERACTIONS")

    for idx, filename in enumerate(all_files, 1):
        file_path = os.path.join(target_folder, filename)
        file_id = filename.replace(".pdf", "")
        start_time = time.time()
        
        print(f"\n{'='*80}")
        print(f"📁 [{idx}/{len(all_files)}] Processing: {filename}")
        print(f"{'='*80}")
        
        # Extract drug interactions
        drug_names = extract_drug_interactions_from_pdf(file_path, filename)
        
        folder_dataset.append({
            "ID": file_id,
            "Drug Interactions": drug_names
        })
        
        # Print result
        print(f"\n  {'-'*40}")
        print(f"  ✅ FINISHED: {filename}")
        if drug_names and drug_names not in ["NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED", "ERROR"]:
            if drug_names == "******":
                print(f"     Status: No drug interactions found")
            else:
                drug_count = len(drug_names.split(','))
                print(f"     Found {drug_count} interacting drugs")
                print(f"     Drugs: {drug_names[:100]}..." if len(drug_names) > 100 else f"     Drugs: {drug_names}")
        else:
            print(f"     Status: {drug_names}")
        print(f"  {'-'*40}")

        # Enforce RPM safety
        elapsed = time.time() - start_time
        if elapsed < SAFE_DELAY:
            time.sleep(SAFE_DELAY - elapsed)

    # Save results to Excel
    if folder_dataset:
        # Create output folder if it doesn't exist
        if not os.path.exists(INTERACTIONS_OUTPUT_FOLDER):
            os.makedirs(INTERACTIONS_OUTPUT_FOLDER)
            print(f"\n  📁 Created folder: {INTERACTIONS_OUTPUT_FOLDER}")

        # Save to Excel
        df = pd.DataFrame(folder_dataset)
        output_filename = os.path.join(INTERACTIONS_OUTPUT_FOLDER, f"{folder_name}_drug_interactions.xlsx")
        df.to_excel(output_filename, index=False)
        print(f"\n💾 Saved {len(folder_dataset)} records to {output_filename}")
        
        # Print summary
        print(f"\n📊 SUMMARY - DRUG INTERACTIONS:")
        success_count = sum(1 for item in folder_dataset if item['Drug Interactions'] not in 
                          ["NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED", "ERROR"])
        no_interactions_count = sum(1 for item in folder_dataset if item['Drug Interactions'] == "******")
        
        print(f"  ✅ Successfully extracted: {success_count}/{len(folder_dataset)} files")
        print(f"  ℹ️  No interactions found: {no_interactions_count}/{len(folder_dataset)} files")
        
        # Show sample of successful extractions
        if success_count > 0:
            print(f"\n  Sample successful extractions:")
            shown = 0
            for item in folder_dataset:
                if item['Drug Interactions'] not in ["NO_TEXT_FOUND", "SECTION_NOT_FOUND", "EXTRACTION_FAILED", "ERROR", "******"]:
                    summary = item['Drug Interactions']
                    if len(summary) > 60:
                        summary = summary[:60] + "..."
                    print(f"    • {item['ID']}: {summary}")
                    shown += 1
                    if shown >= 5:
                        break

# For standalone execution
if __name__ == "__main__":
    # Test the module when run directly
    test_folder = "../Received Monographs/Product monograph/Calcium channel blocker/Amlodipine"
    process_drug_interactions_folder(test_folder)
    
    try:
        beep()
    except:
        pass
    
    print("\n✨ Drug Interactions extraction complete!")