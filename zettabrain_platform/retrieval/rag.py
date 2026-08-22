"""RAG retrieval engine — hybrid search (MMR + BM25 + FlashRank reranking)."""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate

from ..config import CHROMA_DIR

_TEAMS_RAG_PROMPT = """\
You are a precise document assistant for a team workspace.
Answer the question using ONLY the information in the context below.

Rules:
- If the context contains a clear answer, give it directly and concisely.
- If the context does NOT contain enough information to answer the question, \
respond with exactly this phrase and nothing else:
  "This question is outside the scope of this team's document library."
- Never speculate or use knowledge outside the provided context.
- Never list or describe which documents are available.

Context:
{context}

Question: {question}

Answer:"""

_OOS_PHRASES = (
    "outside the scope of this team",
    "i don't have information",
    "i do not have information",
    "not in the document",
    "not mentioned in",
    "no information about",
    "the provided documents do not",
    "the documents don't",
    "the context does not contain",
    "the context doesn't contain",
    "not covered in",
    "cannot find this information",
    "no relevant information",
)

_CONFIDENCE_THRESHOLD = 0.55
_MIN_RERANK_LOGIT = -0.5
_SUPPORTED_EXTS = {".pdf", ".txt", ".docx", ".doc", ".md"}


def _is_out_of_scope(answer: str) -> bool:
    lower = answer.lower()
    return any(p in lower for p in _OOS_PHRASES)


def get_vectorstore(
    team_slug: str,
    embed_provider: str,
    embed_model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
) -> Chroma:
    from ..llm.factory import get_embeddings

    path = str(CHROMA_DIR / team_slug)
    Path(path).mkdir(parents=True, exist_ok=True)

    embeddings = get_embeddings(
        provider=embed_provider,
        model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
    )

    return Chroma(
        persist_directory=path,
        embedding_function=embeddings,
        collection_name="zettabrain_docs",
    )


def _team_bm25_path(team_slug: str) -> Path:
    return CHROMA_DIR / team_slug / "bm25_index.pkl"


def _rebuild_team_bm25(vectorstore, team_slug: str) -> int:
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return 0
    try:
        result    = vectorstore._collection.get(include=["documents", "metadatas"])
        docs      = result["documents"]
        metadatas = result["metadatas"]
        if not docs:
            return 0
        bm25 = BM25Okapi([d.lower().split() for d in docs])
        bm25_path = _team_bm25_path(team_slug)
        bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(bm25_path, "wb") as f:
            pickle.dump({"bm25": bm25, "docs": docs, "metadatas": metadatas}, f)
        return len(docs)
    except Exception:
        return 0


def _bm25_search_team(query: str, team_slug: str, k: int = 8) -> list:
    try:
        from rank_bm25 import BM25Okapi
        from langchain_core.documents import Document
    except ImportError:
        return []
    bm25_path = _team_bm25_path(team_slug)
    if not bm25_path.exists():
        return []
    try:
        with open(bm25_path, "rb") as f:
            data = pickle.load(f)
        tokens = query.lower().split()
        scores = data["bm25"].get_scores(tokens)
        max_score = float(scores.max()) if len(scores) else 0.0
        if max_score <= 0:
            return []
        min_score = max_score * 0.20
        top = scores.argsort()[-(min(k, len(scores))):][::-1]
        return [
            Document(page_content=data["docs"][i], metadata=data["metadatas"][i])
            for i in top if scores[i] >= min_score
        ]
    except Exception:
        return []


def _hybrid_retrieve(question: str, vectorstore, team_slug: str, top_k: int = 5) -> tuple:
    semantic = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 6, "fetch_k": 20, "lambda_mult": 0.82},
    ).invoke(question)

    keyword = _bm25_search_team(question, team_slug, k=8)

    seen, merged = set(), []
    for doc in semantic + keyword:
        key = hashlib.md5(doc.page_content.encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            merged.append(doc)

    try:
        from flashrank import Ranker, RerankRequest
        ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
        if merged:
            passages = [{"id": i, "text": d.page_content} for i, d in enumerate(merged)]
            ranked   = ranker.rerank(RerankRequest(query=question, passages=passages))
            above_threshold = [r for r in ranked if r["score"] >= _MIN_RERANK_LOGIT]
            selected = (above_threshold or ranked[:1])[:top_k]
            top_docs  = [merged[r["id"]] for r in selected]
            top_score = float(selected[0]["score"]) if selected else None
            return top_docs, top_score
    except Exception:
        pass

    return merged[:top_k], None


def _score_confidence(docs: list, answer: str, rerank_score: float = None) -> float:
    import math

    if not docs or _is_out_of_scope(answer):
        return 0.0

    if rerank_score is not None:
        normalized = 1.0 / (1.0 + math.exp(-rerank_score))
        return round(min(1.0, normalized), 3)

    filled = sum(1 for d in docs if len(d.page_content.strip()) > 50)
    return round(filled / len(docs), 3)


def _format_context(docs: list) -> str:
    parts = []
    for i, doc in enumerate(docs, 1):
        source = Path(doc.metadata.get("source", "unknown")).name
        parts.append(f"[Document {i}: {source}]\n{doc.page_content}")
    return "\n\n".join(parts)


def query_team(
    team_slug: str,
    question: str,
    llm_provider: str,
    embed_provider: str,
    llm_model: str,
    embed_model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    cloud_api_key: Optional[str] = None,
) -> dict:
    """Query a team's document library."""
    from ..llm.factory import get_chat_llm

    vectorstore = get_vectorstore(
        team_slug=team_slug,
        embed_provider=embed_provider,
        embed_model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
    )

    try:
        doc_count = vectorstore._collection.count()
    except Exception:
        doc_count = 0

    if doc_count == 0:
        return {
            "answer":          "No documents have been ingested for this team yet.",
            "confidence":      0.0,
            "chunks":          0,
            "duration_ms":     0,
            "sources":         [],
            "below_threshold": True,
        }

    t0   = time.time()
    docs, rerank_score = _hybrid_retrieve(question, vectorstore, team_slug)

    llm = get_chat_llm(
        provider=llm_provider,
        model=llm_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        cloud_api_key=cloud_api_key,
    )

    prompt  = PromptTemplate.from_template(_TEAMS_RAG_PROMPT)
    context = _format_context(docs)
    response = llm.invoke(prompt.format(context=context, question=question))

    if hasattr(response, 'content'):
        answer = response.content.strip() if isinstance(response.content, str) else str(response.content).strip()
    else:
        answer = response.strip() if isinstance(response, str) else str(response).strip()

    duration_ms = int((time.time() - t0) * 1000)
    oos         = _is_out_of_scope(answer)
    confidence  = _score_confidence(docs, answer, rerank_score)

    if oos:
        answer  = "This question is outside the scope of this team's document library."
        sources = []
        docs    = []
    else:
        seen_src: set = set()
        sources: list = []
        for d in docs:
            name = Path(d.metadata.get("source", "unknown")).name
            if name not in seen_src:
                seen_src.add(name)
                sources.append(name)

    query_hash   = hashlib.sha256(question.encode()).hexdigest()
    chunk_hashes = [hashlib.sha256(d.page_content.encode()).hexdigest() for d in docs]
    answer_hash  = hashlib.sha256(answer.encode()).hexdigest()

    return {
        "answer":          answer,
        "confidence":      confidence,
        "chunks":          len(docs),
        "duration_ms":     duration_ms,
        "sources":         sources,
        "below_threshold": confidence < _CONFIDENCE_THRESHOLD,
        "query_hash":      query_hash,
        "chunk_hashes":    chunk_hashes,
        "answer_hash":     answer_hash,
    }
