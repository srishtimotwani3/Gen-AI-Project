import requests
from bs4 import BeautifulSoup
import arxiv
import re
from .pdf_parser import parse_pdf_bytes

def parse_url(url: str) -> dict:
    """
    Parse a URL and return a dict with 'title' and 'text'.
    Handles ArXiv, PDF links, and generic HTML pages.
    """
    try:
        # ArXiv URL handling
        if "arxiv.org" in url:
            match = re.search(r'(?:abs|pdf)/(\d+\.\d+)', url)
            if match:
                arxiv_id = match.group(1)
                search = arxiv.Search(id_list=[arxiv_id])
                paper = next(search.results())
                
                # Fetch PDF content
                pdf_url = paper.pdf_url
                response = requests.get(pdf_url)
                response.raise_for_status()
                text = parse_pdf_bytes(response.content)
                
                return {
                    "title": paper.title,
                    "text": text
                }
        
        # Direct PDF link handling
        if url.lower().endswith(".pdf"):
            response = requests.get(url)
            response.raise_for_status()
            text = parse_pdf_bytes(response.content)
            # Try to get a title from URL or leave empty
            title = url.split("/")[-1]
            return {
                "title": title,
                "text": text
            }
            
        # Generic HTML page handling
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")
        
        # Extract title
        title = soup.title.string if soup.title else "Unknown Title"
        
        # Extract text (heuristically stripping boilerplate)
        # For a more robust approach, libraries like readability-lxml could be used
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
        
        text = soup.get_text(separator="\n")
        # Collapse whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return {
            "title": title.strip(),
            "text": text.strip()
        }
    except Exception as e:
        raise RuntimeError(f"Error parsing URL {url}: {str(e)}")
