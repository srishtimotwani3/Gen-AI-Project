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
        # Enrich query to bias towards research papers
        enriched_query = f"{query} research paper academic"
        response = client.search(enriched_query, search_depth="basic", max_results=limit)
        
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
