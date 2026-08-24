"""Document generation router — skill-based AI document generation per team."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..config import SKILLS_DIR
from ..deps import CurrentUser, SessionDep, get_team_membership
from ..generation.engine import GenerationEngine
from ..generation.models import GenerationRequest, Skill
from ..generation.skill_parser import SkillParser, load_skill

router = APIRouter(prefix="/api/teams", tags=["generate"])


class GenerateBody(BaseModel):
    input: str
    skill_name: str
    context: Dict[str, Any] = {}
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class SkillUploadBody(BaseModel):
    content: str
    filename: str


@router.get("/{team_id}/skills")
def list_skills(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    """List available skills for a team."""
    get_team_membership(team_id, current_user, session)

    skills = []
    skills_path = SKILLS_DIR
    if skills_path.exists():
        for f in sorted(skills_path.glob("*.md")):
            try:
                skill = SkillParser.parse_file(f)
                skills.append({
                    "name": skill.name,
                    "version": skill.version,
                    "description": skill.description,
                    "business_type": skill.business_type,
                    "requires_corpus": skill.requires_corpus,
                    "tags": skill.tags,
                })
            except Exception:
                continue

    # Also check team-specific skills
    from ..models import Team
    team = session.get(Team, team_id)
    if team:
        team_skills_path = SKILLS_DIR / team.slug
        if team_skills_path.exists():
            for f in sorted(team_skills_path.glob("*.md")):
                try:
                    skill = SkillParser.parse_file(f)
                    skills.append({
                        "name": skill.name,
                        "version": skill.version,
                        "description": skill.description,
                        "business_type": skill.business_type,
                        "requires_corpus": skill.requires_corpus,
                        "tags": skill.tags,
                        "team_specific": True,
                    })
                except Exception:
                    continue

    return {"skills": skills}


@router.post("/{team_id}/generate")
def generate_document(
    team_id: int,
    body: GenerateBody,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Generate a document using a skill."""
    membership = get_team_membership(team_id, current_user, session)

    from ..models import Team
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Find the skill file
    skill_file = _find_skill_file(body.skill_name, team.slug)
    if not skill_file:
        raise HTTPException(status_code=404, detail=f"Skill '{body.skill_name}' not found")

    skill = load_skill(skill_file)

    # Build corpus retriever if skill requires it
    corpus_retriever = None
    if skill.requires_corpus:
        corpus_retriever = _build_corpus_retriever(team, session)

    engine = GenerationEngine(corpus_retriever=corpus_retriever)

    request = GenerationRequest(
        input=body.input,
        skill_name=body.skill_name,
        business_id=team.slug,
        context=body.context,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )

    result = engine.generate(skill, request)

    if not result.success:
        raise HTTPException(status_code=500, detail=f"Generation failed: {result.error}")

    return {
        "id": result.id,
        "content": result.content,
        "skill_name": result.skill_name,
        "skill_version": result.skill_version,
        "citations": result.citations,
        "generation_time_ms": result.generation_time_ms,
        "metadata": result.metadata,
    }


@router.post("/{team_id}/skills/upload")
def upload_skill(
    team_id: int,
    body: SkillUploadBody,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Upload a custom skill for a team (manager only)."""
    from ..models import Team, TeamRole
    membership = get_team_membership(team_id, current_user, session)
    if membership.team_role != TeamRole.manager:
        raise HTTPException(status_code=403, detail="Team manager role required")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Validate the skill content
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
        tmp.write(body.content)
        tmp_path = tmp.name

    try:
        skill = SkillParser.parse_and_validate(tmp_path)
    except (ValueError, FileNotFoundError) as e:
        Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Save to team skills directory
    team_skills_dir = SKILLS_DIR / team.slug
    team_skills_dir.mkdir(parents=True, exist_ok=True)

    filename = body.filename if body.filename.endswith(".md") else f"{body.filename}.md"
    skill_path = team_skills_dir / filename
    skill_path.write_text(body.content, encoding="utf-8")

    return {
        "message": f"Skill '{skill.name}' uploaded successfully",
        "skill": {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
        },
    }


def _find_skill_file(skill_name: str, team_slug: str) -> Optional[Path]:
    """Find a skill file by name, checking team-specific first then global."""
    # Check team-specific skills first
    team_dir = SKILLS_DIR / team_slug
    if team_dir.exists():
        for f in team_dir.glob("*.md"):
            try:
                skill = SkillParser.parse_file(f)
                if skill.name == skill_name:
                    return f
            except Exception:
                continue

    # Check global skills
    if SKILLS_DIR.exists():
        for f in SKILLS_DIR.glob("*.md"):
            try:
                skill = SkillParser.parse_file(f)
                if skill.name == skill_name:
                    return f
            except Exception:
                continue

    return None


def _build_corpus_retriever(team, session):
    """Build a corpus retriever that uses the team's vectorstore."""
    from ..rag import get_vectorstore, _hybrid_retrieve
    from ..routers.settings import get_setting

    embed_provider = team.embed_provider or get_setting(session, "embed_provider") or "ollama"
    embed_model = team.embed_model or get_setting(session, "embed_model") or "nomic-embed-text"
    ollama_host = get_setting(session, "ollama_host") or "http://localhost:11434"
    openai_key = get_setting(session, "openai_api_key")

    class TeamCorpusRetriever:
        def get_context_for_generation(self, query, n_results=5, min_relevance=0.3, business_type=None):
            vectorstore = get_vectorstore(
                team_slug=team.slug,
                embed_provider=embed_provider,
                embed_model=embed_model,
                ollama_host=ollama_host,
                openai_key=openai_key,
            )
            docs, score = _hybrid_retrieve(query, vectorstore, team.slug, top_k=n_results)
            if not docs:
                return None, []

            from dataclasses import dataclass

            @dataclass
            class Citation:
                document_title: str
                citation_ref: str = ""

            context_parts = ["# CORPUS CONTEXT (from team document library)"]
            citations = []
            for i, doc in enumerate(docs, 1):
                source = Path(doc.metadata.get("source", "unknown")).stem
                context_parts.append(f"\n## Source [{i}]: {source}")
                context_parts.append(doc.page_content)
                citations.append(Citation(document_title=source, citation_ref=f"[{i}]"))

            return "\n".join(context_parts), citations

    return TeamCorpusRetriever()
