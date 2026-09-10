"""Extract adverse events from pharmaceutical monographs."""

import re
from typing import Tuple, Optional
from .config import (
    MAX_SECTION_CHARS,
    TOC_SEARCH_PAGES, DEFAULT_ADVERSE_START_PAGE, 
    DEFAULT_ADVERSE_END_PAGE_OFFSET
)
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api, call_ai_api_keywords
from .prompts import ADVERSE_EVENTS_EXTRACTION_PROMPT, ADVERSE_EVENTS_SYSTEM_MESSAGE

# Regex patterns for finding sections in TOC
ADVERSE_REACTIONS_PATTERNS = [
    r'(\d+\.?\d*)\s+ADVERSE\s+REACTIONS?[^\d]*?\.{2,}\s*(\d+)',
    r'(\d+\.?\d*)\s+ADVERSE\s+REACTIONS?[^\d]*?\s+(\d+)(?:\s|$)',
    r'ADVERSE\s+REACTIONS?[^\d]*?\.{2,}\s*(\d+)',
    r'ADVERSE\s+REACTIONS?[^\d]*?\s+(\d+)(?:\s|$)',
]

NEXT_SECTION_PATTERNS = [
    r'(\d+\.?\d*)\s+DRUG\s+INTERACTIONS?[^\d]*?\.{2,}\s*(\d+)',
    r'(\d+\.?\d*)\s+DRUG\s+INTERACTIONS?[^\d]*?\s+(\d+)(?:\s|$)',
    r'DRUG\s+INTERACTIONS?[^\d]*?\.{2,}\s*(\d+)',
    r'DRUG\s+INTERACTIONS?[^\d]*?\s+(\d+)(?:\s|$)',
]

def find_section_in_toc(pages_text: list, section_name: str, patterns: list) -> Tuple[Optional[int], Optional[str]]:
    """
    Find section start page and number in table of contents.
    
    Args:
        pages_text: List of page dictionaries
        section_name: Name of section to find (for logging)
        patterns: List of regex patterns to match
    
    Returns:
        Tuple of (page_number, section_number) or (None, None)
    """
    # Combine text from first few pages (TOC is usually early)
    toc_text = ""
    for page_data in pages_text[:TOC_SEARCH_PAGES]:
        toc_text += f"\n--- PAGE {page_data['page_num']} ---\n{page_data['text']}\n"
    
    for pattern in patterns:
        matches = re.finditer(pattern, toc_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                section_num, page = match.groups()
                print(f"    ✅ Found {section_name}: Section {section_num} on page {page}")
                return int(page), section_num
            elif len(match.groups()) == 1:
                page = match.group(1)
                print(f"    ✅ Found {section_name} on page {page}")
                return int(page), None
    
    return None, None

def get_adverse_reactions_range(pages_text: list, filename: str) -> Tuple[int, int]:
    """
    Determine page range for Adverse Reactions section.
    
    Args:
        pages_text: List of page dictionaries
        filename: Name of file (for logging)
    
    Returns:
        Tuple of (start_page, end_page)
    """
    print(f"  🔍 Searching for Adverse Reactions section...")
    
    # Find start page
    start_page, section_num = find_section_in_toc(pages_text, "Adverse Reactions", ADVERSE_REACTIONS_PATTERNS)
    
    if not start_page:
        print(f"  ⚠️ Using default start page {DEFAULT_ADVERSE_START_PAGE}")
        start_page = DEFAULT_ADVERSE_START_PAGE
    
    # Find end page
    print(f"    🔍 Searching for next section...")
    end_page, _ = find_section_in_toc(pages_text, "Drug Interactions", NEXT_SECTION_PATTERNS)
    
    if not end_page:
        end_page = start_page + DEFAULT_ADVERSE_END_PAGE_OFFSET
        print(f"  ⚠️ Using default end page {end_page}")
    
    return start_page, end_page

def extract_adverse_reactions_section(pages_text: list, start_page: int, end_page: int) -> Optional[str]:
    """
    Extract content from Adverse Reactions section focusing on the start page header.
    
    Args:
        pages_text: List of page dictionaries
        start_page: Starting page number
        end_page: Ending page number
    
    Returns:
        Extracted text or None if no content
    """
    print(f"    📄 Extracting pages {start_page} to {end_page}")
    adverse_content = []
    
    for page_data in pages_text:
        page_num = page_data['page_num']
        
        if page_num < start_page:
            continue
        if page_num > end_page:
            break
        
        page_header = f"\n--- PAGE {page_num} ---\n"
        
        if page_num == start_page:
            # Start from the section header on the first page
            lines = page_data['text'].split('\n')
            found_header = False
            page_content = []
            
            for line in lines:
                if not found_header and re.search(r'ADVERSE\s+REACTIONS?', line, re.IGNORECASE):
                    found_header = True
                    page_content.append(line)
                elif found_header:
                    page_content.append(line)
            
            if page_content:
                adverse_content.append(page_header + '\n'.join(page_content))
        else:
            adverse_content.append(page_header + page_data['text'])
    
    return '\n'.join(adverse_content) if adverse_content else None

def extract_adverse_events(pdf_path: str, filename: str) -> str:
    """
    Extract adverse events as comma-separated list.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of file (for logging)
    
    Returns:
        Comma-separated list of adverse events or error message
    """
    # Extract all pages with metadata
    pages_text = extract_pdf_text(pdf_path, pages=None)
    
    if not pages_text:
        return "NO_TEXT_FOUND"
    
    # Find page range for Adverse Reactions
    start_page, end_page = get_adverse_reactions_range(pages_text, filename)
    
    # Extract content from that range
    adverse_section = extract_adverse_reactions_section(pages_text, start_page, end_page)
    
    if not adverse_section:
        return "CONTENT_EXTRACTION_FAILED"
    
    # Extract event names using AI
    prompt = ADVERSE_EVENTS_EXTRACTION_PROMPT.format(
        adverse_section=adverse_section[:MAX_SECTION_CHARS]
    )
    result = call_ai_api_keywords(
        prompt, ADVERSE_EVENTS_SYSTEM_MESSAGE, filename, "Adverse Events",
        source_text=adverse_section[:MAX_SECTION_CHARS], temperature=0.1
    )
    
    if result:
        # Clean up the result
        result = re.sub(r'\s+', ' ', result.strip())
        result = re.sub(r',\s*', ', ', result)
        event_count = len(result.split(',')) if result not in ["NO_ADVERSE_EVENTS_FOUND", "EXTRACTION_FAILED"] else 0
        print(f"  ✅ Found {event_count} adverse events")
        return result
    
    return "EXTRACTION_FAILED"