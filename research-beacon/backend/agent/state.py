from typing import TypedDict, Optional

class AgentState(TypedDict):
    paper_text: str          # Full extracted text
    paper_title: str         # Detected/extracted title
    source_type: str         # "pdf" | "url"
    source_ref: str          # Original URL or filename
    summary: str
    key_findings: str
    methodology: str
    limitations_future: str
    related_papers: list[dict]  # [{title, url, snippet}]
    qa_history: list[dict]   # [{question, answer}]
    error: Optional[str]
