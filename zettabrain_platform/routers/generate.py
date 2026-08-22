"""Generative AI endpoint — skill-based document generation with team auth."""

from __future__ import annotations

import glob
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import select

from ..config import SKILLS_DIR
from ..deps import CurrentUser, SessionDep
from ..generation.engine import GenerationEngine
from ..generation.models import GenerationRequest
from ..generation.skill_parser import load_skill
from ..models import (
    AuditLog, GeneratedDocument, GenerateRequest, GenerateResponse,
    SystemRole, Team, TeamMember,
)

router = APIRouter(prefix="/api/generate", tags=["generate"])


def _get_team_skills_dir(team_slug: str) -> Path:
    """Team-scoped skills directory with fallback to shared."""
    team_dir = SKILLS_DIR / team_slug
    if team_dir.exists():
        return team_dir
    return SKILLS_DIR


def _load_skills(team_slug: str = "") -> List[Dict[str, Any]]:
    skills_dir = _get_team_skills_dir(team_slug) if team_slug else SKILLS_DIR
    skills = []
    for skill_file in sorted(glob.glob(str(skills_dir / "*.md"))):
        try:
            skill = load_skill(skill_file)
            variables = list(set(re.findall(r"\{\{(\w+)\}\}", skill.instructions)))
            skills.append({
                "file": skill_file,
                "name": skill.name,
                "display_name": skill.name.replace("-", " ").title(),
                "description": skill.description,
                "business_type": skill.business_type,
                "version": skill.version,
                "requires_corpus": skill.requires_corpus,
                "citation_required": skill.citation_required,
                "variables": variables,
            })
        except Exception:
            continue

    # Also include shared skills if team has its own directory
    if team_slug and (SKILLS_DIR / team_slug).exists():
        for skill_file in sorted(glob.glob(str(SKILLS_DIR / "*.md"))):
            try:
                skill = load_skill(skill_file)
                variables = list(set(re.findall(r"\{\{(\w+)\}\}", skill.instructions)))
                skills.append({
                    "file": skill_file,
                    "name": skill.name,
                    "display_name": skill.name.replace("-", " ").title(),
                    "description": skill.description,
                    "business_type": skill.business_type,
                    "version": skill.version,
                    "requires_corpus": skill.requires_corpus,
                    "citation_required": skill.citation_required,
                    "variables": variables,
                    "shared": True,
                })
            except Exception:
                continue

    return skills


def _get_engine() -> GenerationEngine:
    return GenerationEngine()


@router.get("/skills")
def list_skills(current_user: CurrentUser, session: SessionDep):
    """List available skills."""
    return _load_skills()


@router.post("/", response_model=GenerateResponse)
def generate_document(
    body: GenerateRequest,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Generate a document using a skill (team-scoped, authenticated)."""
    team = session.get(Team, body.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if not team.skills_enabled:
        raise HTTPException(status_code=403, detail="Document generation is disabled for this team")

    membership = session.exec(
        select(TeamMember).where(
            TeamMember.user_id == current_user.id,
            TeamMember.team_id == body.team_id,
        )
    ).first()
    if current_user.system_role != SystemRole.admin and not membership:
        raise HTTPException(status_code=403, detail="Not a team member")

    skill_path = Path(body.skill_file)
    if not skill_path.exists():
        raise HTTPException(status_code=400, detail=f"Skill file not found: {body.skill_file}")

    skill = load_skill(str(skill_path))
    engine = _get_engine()

    if not engine.llm_provider.check_health():
        raise HTTPException(status_code=503, detail="LLM provider is not running")

    today = datetime.now()
    parts = [f"TODAY'S DATE: {today.strftime('%B %d, %Y')}\n\n"]
    if body.customer_name:
        parts.append(f"Customer/Client: {body.customer_name}\n")
    if body.customer_email:
        parts.append(f"Email: {body.customer_email}\n")
    if body.customer_phone:
        parts.append(f"Phone: {body.customer_phone}\n")
    if body.customer_name or body.customer_email or body.customer_phone:
        parts.append("\n")
    parts.append(body.input_text)

    gen_request = GenerationRequest(
        input="".join(parts),
        skill_name=skill.name,
        business_id=team.slug,
    )

    result = engine.generate(skill, gen_request)

    if not result.success:
        raise HTTPException(status_code=500, detail=f"Generation failed: {result.error}")

    # Persist to database
    doc = GeneratedDocument(
        id=result.id,
        team_id=team.id,
        user_id=current_user.id,
        skill_name=skill.name,
        skill_display=skill.name.replace("-", " ").title(),
        customer_name=body.customer_name or "Customer",
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        request=body.input_text,
        content=result.content,
        citations=json.dumps(result.citations) if result.citations else None,
        generation_time_ms=result.generation_time_ms,
    )
    session.add(doc)

    log = AuditLog(
        user_id=current_user.id,
        team_id=team.id,
        action="generate",
        query=body.input_text[:200],
        response_preview=result.content[:200],
        model=getattr(engine.llm_provider, "model", "unknown"),
        duration_ms=result.generation_time_ms,
        skill_name=skill.name,
        document_id=result.id,
    )
    session.add(log)
    session.commit()

    return GenerateResponse(
        id=result.id,
        skill_name=skill.name,
        content=result.content,
        citations=result.citations,
        generation_time_ms=result.generation_time_ms,
    )


@router.get("/documents")
def list_documents(
    current_user: CurrentUser,
    session: SessionDep,
    team_id: int = None,
    limit: int = 50,
):
    """List generated documents for the current user (optionally filtered by team)."""
    query = select(GeneratedDocument)
    if current_user.system_role != SystemRole.admin:
        query = query.where(GeneratedDocument.user_id == current_user.id)
    if team_id:
        query = query.where(GeneratedDocument.team_id == team_id)
    query = query.order_by(GeneratedDocument.created_at.desc()).limit(limit)
    docs = session.exec(query).all()
    return [
        {
            "id": d.id,
            "team_id": d.team_id,
            "skill_name": d.skill_name,
            "skill_display": d.skill_display,
            "customer_name": d.customer_name,
            "request": d.request[:100],
            "citations": json.loads(d.citations) if d.citations else [],
            "generation_time_ms": d.generation_time_ms,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, current_user: CurrentUser, session: SessionDep):
    """Get a generated document by ID."""
    doc = session.get(GeneratedDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if current_user.system_role != SystemRole.admin and doc.user_id != current_user.id:
        membership = session.exec(
            select(TeamMember).where(
                TeamMember.user_id == current_user.id,
                TeamMember.team_id == doc.team_id,
            )
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": doc.id,
        "team_id": doc.team_id,
        "skill_name": doc.skill_name,
        "skill_display": doc.skill_display,
        "customer_name": doc.customer_name,
        "customer_email": doc.customer_email,
        "customer_phone": doc.customer_phone,
        "request": doc.request,
        "content": doc.content,
        "citations": json.loads(doc.citations) if doc.citations else [],
        "generation_time_ms": doc.generation_time_ms,
        "created_at": doc.created_at.isoformat(),
    }


@router.websocket("/ws/stream")
async def ws_generate(websocket: WebSocket):
    """WebSocket endpoint for streaming document generation."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            skill_file = data.get("skill_file")
            input_text = data.get("input_text", "")
            customer_name = data.get("customer_name", "")

            if not skill_file or not input_text:
                await websocket.send_json({"type": "error", "message": "skill_file and input_text required"})
                continue

            skill_path = Path(skill_file)
            if not skill_path.exists():
                await websocket.send_json({"type": "error", "message": f"Skill not found: {skill_file}"})
                continue

            try:
                skill = load_skill(str(skill_path))
                engine = _get_engine()

                if not engine.llm_provider.check_health():
                    await websocket.send_json({"type": "error", "message": "LLM provider is not running"})
                    continue

                await websocket.send_json({"type": "status", "message": "Generating..."})

                today = datetime.now()
                parts = [f"TODAY'S DATE: {today.strftime('%B %d, %Y')}\n\n"]
                if customer_name:
                    parts.append(f"Customer/Client: {customer_name}\n\n")
                parts.append(input_text)

                gen_request = GenerationRequest(input="".join(parts), skill_name=skill.name)
                prompt = engine.build_prompt(skill, "".join(parts), gen_request.context, None)

                start_time = time.time()
                full_content = ""

                try:
                    for token in engine.llm_provider.stream(
                        prompt=prompt,
                        temperature=skill.temperature,
                        max_tokens=skill.max_tokens,
                    ):
                        full_content += token
                        await websocket.send_json({"type": "token", "token": token})
                except NotImplementedError:
                    full_content = engine.llm_provider.generate(
                        prompt=prompt,
                        temperature=skill.temperature,
                        max_tokens=skill.max_tokens,
                    )
                    await websocket.send_json({"type": "token", "token": full_content})

                generation_time_ms = int((time.time() - start_time) * 1000)
                doc_id = str(uuid.uuid4())

                await websocket.send_json({
                    "type": "done",
                    "id": doc_id,
                    "skill": skill.name,
                    "generation_time_ms": generation_time_ms,
                    "model": getattr(engine.llm_provider, "model", "unknown"),
                })

            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
