"""Unified document ingestion pipeline — reads, chunks, and stores in ChromaDB per team."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import CHROMA_DIR, team_chroma_path
from ..retrieval.rag import _rebuild_team_bm25, get_vectorstore

_SUPPORTED_EXTS = {".pdf", ".txt", ".docx", ".doc", ".md"}


def ingest_team_docs(
    team_slug: str,
    folder: str,
    embed_provider: str,
    embed_model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
) -> dict:
    """Ingest documents into a team's vectorstore."""
    from langchain_community.document_loaders import PyPDFLoader, TextLoader

    vectorstore = get_vectorstore(
        team_slug=team_slug,
        embed_provider=embed_provider,
        embed_model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
    )

    folder_path     = Path(folder)
    chroma_path     = Path(team_chroma_path(team_slug))
    hash_cache_path = chroma_path / "ingested_files.json"

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

    chroma_path.mkdir(parents=True, exist_ok=True)
    hash_cache_path.write_text(json.dumps(hash_cache, indent=2))

    _rebuild_team_bm25(vectorstore, team_slug)

    total_chunks = vectorstore._collection.count()

    return {
        "files_found":    len(files),
        "files_ingested": ingested,
        "files_skipped":  skipped,
        "total_chunks":   total_chunks,
        "errors":         errors,
    }
