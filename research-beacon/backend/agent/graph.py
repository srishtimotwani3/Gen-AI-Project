from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    extract_text_node,
    analyze_paper_node,
    related_papers_node,
    qa_node
)

def build_analysis_graph():
    """Builds the sequential LangGraph for full paper analysis."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("extract_text", extract_text_node)
    workflow.add_node("analyze_paper", analyze_paper_node)
    workflow.add_node("related_papers", related_papers_node)

    # Sequential edges: extract → analyze → related papers → done
    workflow.add_edge("extract_text", "analyze_paper")
    workflow.add_edge("analyze_paper", "related_papers")
    workflow.add_edge("related_papers", END)

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
