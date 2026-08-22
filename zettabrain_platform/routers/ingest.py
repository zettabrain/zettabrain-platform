"""Document ingestion endpoint — ingest team documents into vector store."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import SQLModel, select

from ..deps import CurrentUser, SessionDep, get_team_membership
from ..ingestion.pipeline import ingest_team_docs
from ..models import AuditLog, SystemRole, Team, TeamMember, TeamRole

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class IngestRequest(SQLModel):
    folder: Optional[str] = None


def _can_ingest(membership: TeamMember) -> bool:
    return membership.team_role in (TeamRole.manager,)


@router.post("/{team_id}")
def trigger_ingest(
    team_id: int,
    body: IngestRequest,
    membership: Annotated[TeamMember, Depends(get_team_membership)],
    session: SessionDep,
):
    if not _can_ingest(membership):
        raise HTTPException(status_code=403, detail="Manager role required to ingest")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    folder = body.folder if body.folder else team.docs_folder
    if not folder:
        raise HTTPException(
            status_code=400,
            detail="No docs folder specified. Set docs_folder on the team or pass folder in request body.",
        )

    from pathlib import Path
    if not Path(folder).exists():
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")

    from ..llm.model_resolver import resolve_team_models
    config = resolve_team_models(session, team.id)

    try:
        result = ingest_team_docs(
            team_slug=team.slug,
            folder=folder,
            embed_provider=config["embed_provider"],
            embed_model=config["embed_model"],
            ollama_host=config["ollama_host"],
            openai_key=config["openai_key"],
        )
        output = (
            f"Ingested {result['files_ingested']} file(s), "
            f"skipped {result['files_skipped']} unchanged. "
            f"Total chunks in store: {result['total_chunks']}."
        )
        if result["errors"]:
            output += f" Errors: {'; '.join(result['errors'][:3])}"
    except Exception as e:
        if "dimension" in str(e).lower() and "expecting" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Vector dimension mismatch — clear vector store and re-ingest with the new provider.",
            )
        raise HTTPException(status_code=400, detail=f"Ingest failed: {str(e)[:200]}")

    log = AuditLog(
        user_id          = membership.user_id,
        team_id          = team_id,
        action           = "ingest",
        query            = folder,
        response_preview = output[:200],
    )
    session.add(log)
    session.commit()

    return {"status": "ok", "output": output, "details": result}


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".doc"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB per file


@router.post("/upload")
async def upload_and_ingest(
    team_id: int = Form(...),
    files: List[UploadFile] = File(...),
    current_user: CurrentUser = None,
    session: SessionDep = None,
):
    """Upload files and ingest them into the team's vector store."""
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.system_role != SystemRole.admin:
        membership = session.exec(
            select(TeamMember).where(
                TeamMember.user_id == current_user.id,
                TeamMember.team_id == team_id,
            )
        ).first()
        if not membership or membership.team_role not in (TeamRole.manager,):
            raise HTTPException(status_code=403, detail="Manager role required to ingest")

    for f in files:
        ext = Path(f.filename).suffix.lower() if f.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed: {f.filename}. Supported: {', '.join(ALLOWED_EXTENSIONS)}",
            )

    tmp_dir = tempfile.mkdtemp(prefix="zbp_ingest_")
    try:
        for f in files:
            dest = Path(tmp_dir) / f.filename
            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File too large: {f.filename} (max 50MB)")
            dest.write_bytes(content)

        from ..llm.model_resolver import resolve_team_models

        config = resolve_team_models(session, team.id)
        result = ingest_team_docs(
            team_slug=team.slug,
            folder=tmp_dir,
            embed_provider=config["embed_provider"],
            embed_model=config["embed_model"],
            ollama_host=config["ollama_host"],
            openai_key=config["openai_key"],
        )

        log = AuditLog(
            user_id=current_user.id,
            team_id=team_id,
            action="ingest",
            query=f"upload: {', '.join(f.filename for f in files)}",
            response_preview=f"Ingested {result['files_ingested']} file(s)",
        )
        session.add(log)
        session.commit()

        return {
            "status": "ok",
            "documents_ingested": result["files_ingested"],
            "files_skipped": result["files_skipped"],
            "total_chunks": result["total_chunks"],
            "errors": result.get("errors", []),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
