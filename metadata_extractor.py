"""Extract monograph metadata (brand, company, dates, etc.)."""

from .config import METADATA_PAGES
from .pdf_utils import extract_pdf_text
from .api_client import call_ai_api
from .prompts import METADATA_EXTRACTION_PROMPT, METADATA_SYSTEM_MESSAGE

def extract_metadata(pdf_path: str, filename: str) -> dict:
    """
    Extract monograph metadata from page 1.
    
    Args:
        pdf_path: Path to PDF file
        filename: Name of file (for logging)
    
    Returns:
        Dictionary with metadata fields
    """
    # Extract text from page 1
    pdf_text = extract_pdf_text(pdf_path, pages=METADATA_PAGES)
    
    # Default empty result
    default_metadata = {
        "Brand Name": "NO_TEXT_FOUND",
        "Company": "NO_TEXT_FOUND",
        "Initial Authorization": "NO_TEXT_FOUND",
        "Revision Date": "NO_TEXT_FOUND",
        "Ingredients": "NO_TEXT_FOUND",
        "Dosage": "NO_TEXT_FOUND"
    }
    
    if not pdf_text:
        return default_metadata
    
    # Call AI for extraction
    prompt = METADATA_EXTRACTION_PROMPT.format(pdf_text=pdf_text)
    raw_output = call_ai_api(prompt, METADATA_SYSTEM_MESSAGE, filename)
    
    # Parse response
    extracted_lines = [line.strip() for line in raw_output.strip().split('\n')]
    
    # Ensure exactly 6 fields
    while len(extracted_lines) < 6:
        extracted_lines.append("N/A")
    
    return {
        "Brand Name": extracted_lines[0],
        "Company": extracted_lines[1],
        "Initial Authorization": extracted_lines[2],
        "Revision Date": extracted_lines[3],
        "Ingredients": extracted_lines[4],
        "Dosage": extracted_lines[5]
    }