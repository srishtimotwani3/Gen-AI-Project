from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    extract_text_node,
    summarize_node,
    key_findings_node,
    methodology_node,
    limitations_node,
    related_papers_node,
    qa_node
)

def build_analysis_graph():
    """Builds the sequential LangGraph for full paper analysis."""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("extract_text", extract_text_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("key_findings", key_findings_node)
    workflow.add_node("methodology", methodology_node)
    workflow.add_node("limitations", limitations_node)
    workflow.add_node("related_papers", related_papers_node)
    
    # Define sequential edges
    workflow.add_edge("extract_text", "summarize")
    workflow.add_edge("summarize", "key_findings")
    workflow.add_edge("key_findings", "methodology")
    workflow.add_edge("methodology", "limitations")
    workflow.add_edge("limitations", "related_papers")
    workflow.add_edge("related_papers", END)
    
    # Set entry point
    workflow.set_entry_point("extract_text")
    
    return workflow.compile()

def build_qa_graph():
    """Builds the single-node LangGraph for Q&A."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("qa", qa_node)
    workflow.add_edge("qa", END)
    workflow.set_entry_point("qa")
    
    return workflow.compile()

# Compile graphs once to be imported by FastAPI
analysis_graph = build_analysis_graph()
qa_graph = build_qa_graph()
