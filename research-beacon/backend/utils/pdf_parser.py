import fitz  # PyMuPDF
import io

def parse_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes."""
    text = ""
    try:
        doc = fitz.open("pdf", pdf_bytes)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text()
        return text
    except Exception as e:
        raise RuntimeError(f"Error parsing PDF: {str(e)}")
