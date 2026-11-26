from typing import TypedDict
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser
from tavily import TavilyClient

from src.config import settings
from src.agents.prompts import GRADER_PROMPT, REWRITER_PROMPT, RAG_PROMPT, WEB_SEARCH_PROMPT
from src.retrieval.vector_store import similarity_search
from src.utils.logger import get_logger

log = get_logger(__name__)

class AgentState(TypedDict):
    question: str
    documents: list[Document]
    web_results: list[Document]
    answer: str
    retrieval_source: str
    query_was_rewritten: bool
    rewritten_question: str | None
    generation_count: int

def get_llm(model: str = "openai/gpt-oss-20b"):
    return ChatGroq(model=model, temperature=0, api_key=settings.groq_api_key)

def retrieve(state: AgentState) -> dict:
    log.info("Node: retrieve", question=state["question"][:80])
    documents = similarity_search(query=state["question"], k=settings.retrieval_top_k)
    return {"documents": documents}

def grade_documents(state: AgentState) -> dict:
    question = state["question"]
    documents = state["documents"]
    llm = get_llm()
    chain = GRADER_PROMPT | llm | StrOutputParser()
    relevant = []
    for doc in documents:
        grade = chain.invoke({"question": question, "document": doc.page_content}).strip().lower()
        if grade == "yes":
            relevant.append(doc)
    log.info("Grading done", relevant=len(relevant), total=len(documents))
    return {"documents": relevant}

def rewrite_query(state: AgentState) -> dict:
    original = state["question"]
    llm = get_llm()
    chain = REWRITER_PROMPT | llm | StrOutputParser()
    rewritten = chain.invoke({"question": original}).strip()
    log.info("Query rewritten", original=original, rewritten=rewritten)
    return {"question": rewritten, "rewritten_question": rewritten, "query_was_rewritten": True}

def web_search(state: AgentState) -> dict:
    client = TavilyClient(api_key=settings.tavily_api_key)
    response = client.search(query=state["question"], max_results=3, search_depth="basic")
    web_docs = [
        Document(
            page_content=r.get("content", ""),
            metadata={"source": r.get("url", ""), "doc_name": r.get("title", "Web"), "type": "web"}
        )
        for r in response.get("results", [])
    ]
    return {"web_results": web_docs, "retrieval_source": "web"}

def generate(state: AgentState) -> dict:
    documents = state["documents"]
    web_results = state.get("web_results", [])
    if documents:
        docs_to_use, prompt, source = documents, RAG_PROMPT, "kb"
    elif web_results:
        docs_to_use, prompt, source = web_results, WEB_SEARCH_PROMPT, "web"
    else:
        return {"answer": "I couldn't find relevant information. Please contact IT support directly.", "retrieval_source": "failed"}
    context = "\n\n".join([f"Source: {d.metadata.get('doc_name','unknown')}\nContent: {d.page_content}" for d in docs_to_use])
    llm = get_llm("openai/gpt-oss-20b")
    answer = (prompt | llm | StrOutputParser()).invoke({"context": context, "question": state["question"]})
    return {"answer": answer, "retrieval_source": source}
