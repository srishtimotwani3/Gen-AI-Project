import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from .tools import search_related_papers
from ..utils.pdf_parser import parse_pdf_bytes
from ..utils.url_parser import parse_url

# Initialize Gemini model
def get_model():
    return ChatGoogleGenerativeAI(
        model="gemini-flash-latest",
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.2
    )

def extract_text_node(state: AgentState) -> dict:
    """Extract text based on the source type."""
    if state.get("paper_text"):
        return state # Already extracted
        
    try:
        source_type = state["source_type"]
        source_ref = state["source_ref"]
        
        if source_type == "url":
            result = parse_url(source_ref)
            return {"paper_text": result["text"], "paper_title": result["title"], "error": None}
        elif source_type == "pdf":
            # In real scenario, PDF bytes would be passed or read from temp file
            # For now, we assume paper_text is already populated by FastAPI endpoint for PDFs
            pass
            
    except Exception as e:
        return {"error": f"Failed to extract text: {str(e)}"}
    
    return {}

def analyze_paper_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    model = get_model()
    
    prompt = f"""Analyze the following research paper and extract its key components. 
Respond ONLY with a valid JSON object with the exact following string keys. Ensure the content for each key is highly structured using concise markdown bullet points and headings. 
BE EXTREMELY CONCISE. Cut the analysis short; limit each section to 3-4 brief bullet points maximum.
IMPORTANT: Do NOT use LaTeX (like $ or $$) for mathematical formulas. Instead, you MUST use standard Unicode characters and basic HTML tags like <sub> for subscript and <sup> for superscript (e.g., H<sub>2</sub>O or x<sup>2</sup>). Properly escape all backslashes in your JSON output.
"title": The title of the paper.
"summary": A brief, structured summary (use concise bullet points).
"key_findings": Top contributions and novel results (use concise bullet points).
"methodology": Break down of research design and models (use concise bullet points).
"limitations_future": Limitations and future work (use concise bullet points).
"search_query": A highly effective, semantic search query (5-10 words) based on the core meaning, methodology, and unique findings of the paper. This will be used to find deeply related research papers, NOT just papers with similar titles.

Paper Text (first 25000 chars):
{state['paper_text'][:25000]}
"""
    
    try:
        response = model.invoke([HumanMessage(content=prompt)])
        
        # Handle case where content is a list of blocks
        raw_content = response.content
        if isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "".join(text_parts).strip()
        else:
            content = str(raw_content).strip()
        
        # Clean up markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        import json
        data = json.loads(content.strip())
        
        def to_string(val):
            if isinstance(val, list):
                # If it's a list, join with newlines (useful for bullet points)
                return "\n".join(f"- {item}" if not str(item).startswith("-") else str(item) for item in val)
            elif isinstance(val, dict):
                return json.dumps(val, indent=2)
            return str(val) if val is not None else ""
        
        title = to_string(data.get("title", ""))
        if not title or title.lower() == "unknown":
            title = state.get("paper_title")
            
        return {
            "paper_title": title,
            "search_query": to_string(data.get("search_query", title)),
            "summary": to_string(data.get("summary", "No summary available.")),
            "key_findings": to_string(data.get("key_findings", "No key findings available.")),
            "methodology": to_string(data.get("methodology", "No methodology available.")),
            "limitations_future": to_string(data.get("limitations_future", "No limitations listed."))
        }
    except Exception as e:
        return {"error": f"Failed to analyze paper: {str(e)}"}

def related_papers_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    
    query = state.get("search_query") or state.get("paper_title") or "Unknown paper"
    papers = search_related_papers(query)
    return {"related_papers": papers}

def formatter_agent_node(state: AgentState) -> dict:
    if state.get("error") or not state.get("related_papers"): return {}
    
    model = get_model()
    
    import json
    raw_papers_str = json.dumps(state["related_papers"], indent=2)
    
    prompt = f"""You are an expert formatter. Your task is to clean up messy text snippets extracted from research papers.
The following JSON contains a list of related papers. The 'snippet' fields are often garbled with broken LaTeX (like 'start_POSTSUBSCRIPT' or 'math italic'). 
Fix the garbled snippets so they are easily readable plain text. Do not hallucinate content, just fix the format.
Respond ONLY with a valid JSON array of objects, containing the exact same 'title', 'url', and cleaned 'snippet' fields.

Raw Papers JSON:
{raw_papers_str}
"""
    
    try:
        response = model.invoke([HumanMessage(content=prompt)])
        
        raw_content = response.content
        if isinstance(raw_content, list):
            text_parts = [block["text"] for block in raw_content if isinstance(block, dict) and "text" in block]
            text_parts += [block for block in raw_content if isinstance(block, str)]
            content = "".join(text_parts).strip()
        else:
            content = str(raw_content).strip()
            
        if content.startswith("```json"): content = content[7:]
        elif content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
        
        cleaned_papers = json.loads(content.strip())
        return {"related_papers": cleaned_papers}
    except Exception as e:
        # If formatter fails, just return original papers
        return {}

def qa_node(state: AgentState) -> dict:
    if state.get("error") or not state.get("qa_history"): return {}
    
    model = get_model()
    question = state["qa_history"][-1]["question"]
    
    prompt = f"""Based on the following research paper, answer the user's question. 
If the answer is not in the text, state that.
IMPORTANT: Do NOT use LaTeX (like $ or $$) for mathematical formulas. Instead, you MUST use standard Unicode characters and basic HTML tags like <sub> for subscript and <sup> for superscript (e.g., H<sub>2</sub>O or x<sup>2</sup>).

Paper Text:
{state['paper_text'][:30000]}

Question: {question}"""
    
    response = model.invoke([HumanMessage(content=prompt)])
    
    raw_content = response.content
    if isinstance(raw_content, list):
        text_parts = []
        for block in raw_content:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])
            elif isinstance(block, str):
                text_parts.append(block)
        answer_text = "".join(text_parts).strip()
    else:
        answer_text = str(raw_content).strip()
        
    # Update the last history item with the answer
    history = state["qa_history"].copy()
    history[-1]["answer"] = answer_text
    
    return {"qa_history": history}
