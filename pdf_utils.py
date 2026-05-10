"""PDF text extraction utilities."""

import PyPDF2
from typing import List, Dict, Optional, Union

def extract_pdf_text(pdf_path: str, pages: Optional[List[int]] = None) -> Union[str, List[Dict]]:
    """
    Extract text from PDF.
    
    Args:
        pdf_path: Path to PDF file
        pages: List of 0-indexed page numbers. If None, extracts ALL pages with metadata.
    
    Returns:
        If pages specified: String of concatenated text
        If pages is None: List of dicts with page_num and text
    """
    try:    
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
            
            if pages is not None:
                # Extract specific pages as plain text
                text = ""
                for page_num in pages:
                    if page_num < num_pages:
                        text += reader.pages[page_num].extract_text() + "\n"
                return text.strip()
            else:
                # Extract all pages with metadata
                pages_text = []
                for page_num in range(num_pages):
                    page_text = reader.pages[page_num].extract_text()
                    if page_text:
                        pages_text.append({
                            "page_num": page_num + 1,  # 1-indexed for humans
                            "text": page_text
                        })
                return pages_text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return [] if pages is None else ""

def extract_page_range(pages_text: List[Dict], start_page: int, end_page: int) -> str:
    """
    Extract text from a range of pages.
    
    Args:
        pages_text: List of page dictionaries from extract_pdf_text()
        start_page: Starting page number (1-indexed)
        end_page: Ending page number (1-indexed)
    
    Returns:
        Concatenated text from the page range
    """
    content = []
    for page_data in pages_text:
        page_num = page_data['page_num']
        if start_page <= page_num <= end_page:
            content.append(f"\n--- PAGE {page_num} ---\n{page_data['text']}")
    return '\n'.join(content)