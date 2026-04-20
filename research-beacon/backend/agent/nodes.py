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
        model="gemini-2.0-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
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

def summarize_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    model = get_model()
    prompt = f"Analyze the following research paper and provide a structured summary covering its abstract, purpose, and scope. Be concise and academic.\n\nPaper Text (first 20000 chars):\n{state['paper_text'][:20000]}"
    
    response = model.invoke([HumanMessage(content=prompt)])
    return {"summary": response.content}

def key_findings_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    model = get_model()
    prompt = f"Extract the top contributions, novel results, and key findings from the following research paper. Format as a bulleted list.\n\nPaper Text (first 20000 chars):\n{state['paper_text'][:20000]}"
    
    response = model.invoke([HumanMessage(content=prompt)])
    return {"key_findings": response.content}

def methodology_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    model = get_model()
    prompt = f"Break down the research design, datasets used, and models/algorithms applied in this paper. Explain the methodology clearly.\n\nPaper Text (first 20000 chars):\n{state['paper_text'][:20000]}"
    
    response = model.invoke([HumanMessage(content=prompt)])
    return {"methodology": response.content}

def limitations_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    model = get_model()
    prompt = f"Identify the stated and unstated limitations of this research, as well as suggested future work.\n\nPaper Text (first 20000 chars):\n{state['paper_text'][:20000]}"
    
    response = model.invoke([HumanMessage(content=prompt)])
    return {"limitations_future": response.content}

def related_papers_node(state: AgentState) -> dict:
    if state.get("error"): return {}
    
    title = state.get("paper_title") or "Unknown paper"
    # Fallback to model extracting title if not found
    if title == "Unknown Title" or not title:
        model = get_model()
        prompt = f"What is the title of this paper? Respond with ONLY the title, nothing else.\n\nPaper Text:\n{state['paper_text'][:2000]}"
        response = model.invoke([HumanMessage(content=prompt)])
        title = response.content.strip()
        
    papers = search_related_papers(title)
    return {"related_papers": papers, "paper_title": title}

def qa_node(state: AgentState) -> dict:
    if state.get("error") or not state.get("qa_history"): return {}
    
    model = get_model()
    question = state["qa_history"][-1]["question"]
    
    prompt = f"""Based on the following research paper, answer the user's question. 
If the answer is not in the text, state that.

Paper Text:
{state['paper_text'][:30000]}

Question: {question}"""
    
    response = model.invoke([HumanMessage(content=prompt)])
    
    # Update the last history item with the answer
    history = state["qa_history"].copy()
    history[-1]["answer"] = response.content
    
    return {"qa_history": history}
