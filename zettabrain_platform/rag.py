from __future__ import annotations

import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate

from zettabrain_rag.retrieval import format_context

# Teams-specific prompt — stricter than the base zettabrain-rag prompt.
# Forces the LLM to use the sentinel when it cannot answer from context,
# which lets us zero out confidence and sources programmatically.
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

# Phrases that indicate the LLM could not answer from context
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


def _is_out_of_scope(answer: str) -> bool:
    lower = answer.lower()
    return any(p in lower for p in _OOS_PHRASES)

import re as _re

from .config import CHROMA_DIR, EMBED_MODEL, LLM_MODEL, OLLAMA_HOST, team_chroma_path

_CONFIDENCE_THRESHOLD = 0.55


def _sanitize_model_name(name: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def get_collection_name(
    team_slug: str,
    embed_provider: str,
    embed_model: str,
    multi_embed_enabled: bool,
) -> str:
    if not multi_embed_enabled:
        return "zettabrain_docs"
    sanitized = _sanitize_model_name(embed_model)
    return f"zettabrain_docs_{embed_provider}_{sanitized}"
# Minimum FlashRank logit a chunk must reach to be passed to the LLM.
# sigmoid(-0.5) ≈ 0.38 — filters clearly off-topic chunks while keeping
# borderline-relevant ones that may still help the model.
_MIN_RERANK_LOGIT = -0.5
_SUPPORTED_EXTS = {".pdf", ".txt", ".docx", ".doc", ".md"}

def get_vectorstore(
    team_slug: str,
    embed_provider: str,
    embed_model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    multi_embed_enabled: bool = False,
    collection_name: Optional[str] = None,
) -> Chroma:
    """Create a vectorstore for a team using the configured embedding provider."""
    from .llm_factory import get_embeddings

    path = str(CHROMA_DIR / team_slug)
    Path(path).mkdir(parents=True, exist_ok=True)

    embeddings = get_embeddings(
        provider=embed_provider,
        model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
    )

    col_name = collection_name or get_collection_name(
        team_slug, embed_provider, embed_model, multi_embed_enabled
    )

    return Chroma(
        persist_directory=path,
        embedding_function=embeddings,
        collection_name=col_name,
    )


# ── Per-team BM25 index ───────────────────────────────────────────────────────
# The shared zettabrain_rag.retrieval module keeps a single global BM25 file,
# which causes cross-team document leakage. We maintain one index per team slug
# at {CHROMA_DIR}/{team_slug}/bm25_index.pkl instead.

def _team_bm25_path(team_slug: str, collection_name: str = "zettabrain_docs") -> Path:
    if collection_name == "zettabrain_docs":
        return CHROMA_DIR / team_slug / "bm25_index.pkl"
    return CHROMA_DIR / team_slug / f"{collection_name}_bm25_index.pkl"


def _rebuild_team_bm25(vectorstore, team_slug: str, collection_name: str = "zettabrain_docs") -> int:
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
        bm25_path = _team_bm25_path(team_slug, collection_name)
        bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(bm25_path, "wb") as f:
            pickle.dump({"bm25": bm25, "docs": docs, "metadatas": metadatas}, f)
        return len(docs)
    except Exception:
        return 0


def _bm25_search_team(query: str, team_slug: str, k: int = 8, collection_name: str = "zettabrain_docs") -> list:
    try:
        from rank_bm25 import BM25Okapi
        from langchain_core.documents import Document
    except ImportError:
        return []
    bm25_path = _team_bm25_path(team_slug, collection_name)
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


def _hybrid_retrieve(question: str, vectorstore, team_slug: str, top_k: int = 5, collection_name: str = "zettabrain_docs") -> tuple:
    """Team-scoped hybrid retrieval: MMR + BM25 + FlashRank re-ranking.

    Returns (docs, top_rerank_score_or_None).
    """
    # 1. Semantic MMR — reduced fetch_k to tighten the candidate pool
    semantic = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 6, "fetch_k": 20, "lambda_mult": 0.82},
    ).invoke(question)

    # 2. BM25 keyword search — relative-threshold filtered
    keyword = _bm25_search_team(question, team_slug, k=8, collection_name=collection_name)

    # 3. Merge + deduplicate (semantic first so MMR order is preserved)
    seen, merged = set(), []
    for doc in semantic + keyword:
        key = hashlib.md5(doc.page_content.encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            merged.append(doc)

    # 4. Re-rank and filter by minimum score
    try:
        from flashrank import Ranker, RerankRequest
        ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
        if merged:
            passages = [{"id": i, "text": d.page_content} for i, d in enumerate(merged)]
            ranked   = ranker.rerank(RerankRequest(query=question, passages=passages))

            # Keep only chunks above the minimum logit threshold; always
            # retain at least the top-1 so the OOS path can still trigger.
            above_threshold = [r for r in ranked if r["score"] >= _MIN_RERANK_LOGIT]
            selected = (above_threshold or ranked[:1])[:top_k]

            top_docs  = [merged[r["id"]] for r in selected]
            top_score = float(selected[0]["score"]) if selected else None
            return top_docs, top_score
    except Exception:
        pass

    return merged[:top_k], None


def _score_confidence(docs: list, answer: str, rerank_score: float = None) -> float:
    """Score how well-grounded the answer is in the retrieved chunks.

    Uses the FlashRank cross-encoder top score (sigmoid-normalised to 0–1)
    when available — this is the most reliable signal because it directly
    measures query-chunk relevance.  Falls back to a chunk-fill ratio when
    FlashRank is unavailable.

    Concise correct answers are never penalised — word count is irrelevant
    to whether an answer is grounded in the documents.
    """
    import math

    if not docs or _is_out_of_scope(answer):
        return 0.0

    if rerank_score is not None:
        # Sigmoid of the raw ms-marco logit → interpretable 0–1 probability.
        # Logit ≥ 2  → > 0.88  (strong retrieval match)
        # Logit 0    → 0.50    (borderline)
        # Logit ≤ -2 → < 0.12  (poor match, treat as low confidence)
        normalized = 1.0 / (1.0 + math.exp(-rerank_score))
        return round(min(1.0, normalized), 3)

    # Fallback: proportion of non-trivially-short chunks
    filled = sum(1 for d in docs if len(d.page_content.strip()) > 50)
    return round(filled / len(docs), 3)


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
    multi_embed_enabled: bool = False,
) -> dict:
    """Query a team's document library using the configured LLM and embedding providers."""
    from .llm_factory import get_llm

    col_name = get_collection_name(team_slug, embed_provider, embed_model, multi_embed_enabled)

    vectorstore = get_vectorstore(
        team_slug=team_slug,
        embed_provider=embed_provider,
        embed_model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
        multi_embed_enabled=multi_embed_enabled,
    )

    # Guard: MMR search crashes when collection has fewer docs than fetch_k
    try:
        doc_count = vectorstore._collection.count()
    except Exception:
        doc_count = 0

    # Multi-embed fallback: if model-specific collection is empty, try legacy
    if doc_count == 0 and multi_embed_enabled and col_name != "zettabrain_docs":
        vectorstore = get_vectorstore(
            team_slug=team_slug,
            embed_provider=embed_provider,
            embed_model=embed_model,
            ollama_host=ollama_host,
            openai_key=openai_key,
            collection_name="zettabrain_docs",
        )
        try:
            doc_count = vectorstore._collection.count()
        except Exception:
            doc_count = 0
        if doc_count > 0:
            col_name = "zettabrain_docs"

    if doc_count == 0:
        return {
            "answer":          "No documents have been ingested for this team yet. Ask your admin to ingest the team's documents first.",
            "confidence":      0.0,
            "chunks":          0,
            "duration_ms":     0,
            "sources":         [],
            "below_threshold": True,
        }

    t0   = time.time()
    docs, rerank_score = _hybrid_retrieve(question, vectorstore, team_slug, collection_name=col_name)

    llm = get_llm(
        provider=llm_provider,
        model=llm_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
        anthropic_key=anthropic_key,
    )

    prompt  = PromptTemplate.from_template(_TEAMS_RAG_PROMPT)
    context = format_context(docs)
    response = llm.invoke(prompt.format(context=context, question=question))

    # Handle different response types (string or AIMessage object)
    if hasattr(response, 'content'):
        # AIMessage object (newer models like Claude 4.x)
        answer = response.content.strip() if isinstance(response.content, str) else str(response.content).strip()
    else:
        # Plain string (older models)
        answer = response.strip() if isinstance(response, str) else str(response).strip()

    duration_ms = int((time.time() - t0) * 1000)
    oos         = _is_out_of_scope(answer)
    confidence  = _score_confidence(docs, answer, rerank_score)

    # When the LLM can't answer from context: use a clean fixed message,
    # report zero chunks and no sources so the UI is unambiguous.
    if oos:
        answer  = "This question is outside the scope of this team's document library."
        sources = []
        docs    = []
    else:
        # Sources in ranked order (highest-relevance doc first, no duplicates)
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


# ── In-process document ingestion ────────────────────────────────────────────

def ingest_team_docs(
    team_slug: str,
    folder: str,
    embed_provider: str,
    embed_model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    multi_embed_enabled: bool = False,
) -> dict:
    """Ingest documents into a team's vectorstore using the configured embedding provider."""
    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    col_name = get_collection_name(team_slug, embed_provider, embed_model, multi_embed_enabled)

    vectorstore = get_vectorstore(
        team_slug=team_slug,
        embed_provider=embed_provider,
        embed_model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
        multi_embed_enabled=multi_embed_enabled,
    )

    folder_path     = Path(folder)
    chroma_path     = Path(team_chroma_path(team_slug))
    cache_filename  = f"{col_name}_ingested_files.json" if col_name != "zettabrain_docs" else "ingested_files.json"
    hash_cache_path = chroma_path / cache_filename

    # Load per-team hash cache
    hash_cache: dict = {}
    if hash_cache_path.exists():
        try:
            hash_cache = json.loads(hash_cache_path.read_text())
        except Exception:
            pass

    files = sorted(
        f for f in folder_path.rglob("*")
        if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTS
    )

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    ingested = 0
    skipped  = 0
    errors: List[str] = []

    for f in files:
        filepath = str(f.resolve())
        try:
            file_hash = hashlib.md5(f.read_bytes()).hexdigest()
        except Exception as e:
            errors.append(f"{f.name}: read error: {e}")
            continue

        if hash_cache.get(filepath) == file_hash:
            skipped += 1
            continue

        ext = f.suffix.lower()
        try:
            if ext == ".pdf":
                docs = PyPDFLoader(filepath).load()
            elif ext in {".txt", ".md"}:
                docs = TextLoader(filepath, encoding="utf-8").load()
            elif ext in {".docx", ".doc"}:
                from langchain_community.document_loaders import Docx2txtLoader
                docs = Docx2txtLoader(filepath).load()
            else:
                continue
        except Exception as e:
            errors.append(f"{f.name}: load error: {e}")
            continue

        if not docs:
            errors.append(f"{f.name}: no text extracted")
            continue

        chunks = splitter.split_documents(docs)
        chunks = [c for c in chunks if c.page_content.strip()]

        if not chunks:
            errors.append(f"{f.name}: no chunks after splitting")
            continue

        for chunk in chunks:
            chunk.metadata["source"]   = filepath
            chunk.metadata["filename"] = f.name

        try:
            for i in range(0, len(chunks), 50):
                vectorstore.add_documents(chunks[i : i + 50])
            hash_cache[filepath] = file_hash
            ingested += 1
        except Exception as e:
            errors.append(f"{f.name}: embedding failed: {e}")

    # Persist hash cache
    chroma_path.mkdir(parents=True, exist_ok=True)
    hash_cache_path.write_text(json.dumps(hash_cache, indent=2))

    # Rebuild per-team BM25 keyword index
    _rebuild_team_bm25(vectorstore, team_slug, col_name)

    total_chunks = vectorstore._collection.count()

    return {
        "files_found":    len(files),
        "files_ingested": ingested,
        "files_skipped":  skipped,
        "total_chunks":   total_chunks,
        "errors":         errors,
    }
