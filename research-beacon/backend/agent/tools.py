import os
from tavily import TavilyClient

def search_related_papers(query: str, limit: int = 5) -> list[dict]:
    """
    Search for related academic papers using Tavily with advanced depth
    and strict academic domain filtering.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or api_key == "tvly-your-key-here":
        # Mock response if no real key is configured
        return [
            {
                "title": f"Mock related paper for: {query}",
                "url": "https://example.com/mock-paper",
                "snippet": "This is a mock snippet from Tavily search tool since the API key is missing or invalid."
            }
        ]
        
    try:
        client = TavilyClient(api_key=api_key)
        # Strict academic domains only — no general web results
        academic_domains = [
            "arxiv.org",
            "semanticscholar.org",
            "aclweb.org",
            "aclanthology.org",
            "openreview.net",
            "pubmed.ncbi.nlm.nih.gov",
            "ieee.org",
            "dl.acm.org",
            "nature.com",
            "science.org",
            "springer.com",
            "sciencedirect.com",
            "proceedings.mlr.press",
            "papers.nips.cc",
            "neurips.cc",
            "iclr.cc",
        ]
        response = client.search(
            query,
            search_depth="advanced",
            max_results=limit,
            include_domains=academic_domains
        )
        
        results = []
        for res in response.get("results", []):
            title = res.get("title", "Unknown Title")
            url = res.get("url", "")
            snippet = res.get("content", "")
            
            # Basic filter: skip results that don't look like real paper titles
            # (e.g., homepage links, navigation pages)
            if len(title) < 10 or url.endswith(("/", "/papers", "/search")):
                continue
                
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet
            })
        return results
    except Exception as e:
        print(f"Tavily search error: {e}")
        return []
