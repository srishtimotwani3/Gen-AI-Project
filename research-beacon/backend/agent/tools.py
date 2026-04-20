import os
from tavily import TavilyClient

def search_related_papers(query: str, limit: int = 3) -> list[dict]:
    """
    Search for related academic papers using Tavily.
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
        # Include domains for legitimate academic sources
        academic_domains = [
            "sciencedirect.com", 
            "nature.com", 
            "ieee.org", 
            "springer.com", 
            "arxiv.org", 
            "semanticscholar.org",
            "aclweb.org",
            "pubmed.ncbi.nlm.nih.gov",
            "dl.acm.org"
        ]
        response = client.search(
            query, 
            search_depth="basic", 
            max_results=limit,
            include_domains=academic_domains
        )
        
        results = []
        for res in response.get("results", []):
            results.append({
                "title": res.get("title", "Unknown Title"),
                "url": res.get("url", ""),
                "snippet": res.get("content", "")
            })
        return results
    except Exception as e:
        print(f"Tavily search error: {e}")
        return []
