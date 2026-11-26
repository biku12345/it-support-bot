from langgraph.graph import StateGraph, END
from src.agents.nodes import AgentState, retrieve, grade_documents, rewrite_query, web_search, generate
from src.utils.logger import get_logger

log = get_logger(__name__)

def decide_after_grading(state: AgentState) -> str:
    if state["documents"]:
        return "generate"
    if state.get("query_was_rewritten", False):
        return "web_search"
    return "rewrite_query"

def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_node("web_search", web_search)
    workflow.add_node("generate", generate)
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_edge("rewrite_query", "retrieve")
    workflow.add_conditional_edges("grade_documents", decide_after_grading, {
        "generate": "generate",
        "rewrite_query": "rewrite_query",
        "web_search": "web_search",
    })
    workflow.add_edge("web_search", "generate")
    workflow.add_edge("generate", END)
    return workflow.compile()

graph = build_graph()

def run_agent(question: str) -> dict:
    initial_state: AgentState = {
        "question": question,
        "documents": [],
        "web_results": [],
        "answer": "",
        "retrieval_source": "kb",
        "query_was_rewritten": False,
        "rewritten_question": None,
        "generation_count": 0,
    }
    return graph.invoke(initial_state)
