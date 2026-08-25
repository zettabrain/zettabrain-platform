"""Document generation router — skill-based AI document generation per team."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
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


_BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


@router.get("/{team_id}/skills")
def list_skills(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    """List available skills for a team (built-in + global + team-specific)."""
    get_team_membership(team_id, current_user, session)

    seen_names = set()
    skills = []

    # 1. Team-specific skills (highest priority, marked as team_specific)
    from ..models import Team
    team = session.get(Team, team_id)
    if team:
        team_skills_path = SKILLS_DIR / team.slug
        if team_skills_path.exists():
            for f in sorted(team_skills_path.glob("*.md")):
                try:
                    skill = SkillParser.parse_file(f)
                    if skill.name not in seen_names:
                        seen_names.add(skill.name)
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

    # 2. Global skills in data directory
    if SKILLS_DIR.exists():
        for f in sorted(SKILLS_DIR.glob("*.md")):
            try:
                skill = SkillParser.parse_file(f)
                if skill.name not in seen_names:
                    seen_names.add(skill.name)
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

    # 3. Built-in skills shipped with the package (fallback)
    if _BUILTIN_SKILLS_DIR.exists():
        for f in sorted(_BUILTIN_SKILLS_DIR.glob("*.md")):
            try:
                skill = SkillParser.parse_file(f)
                if skill.name not in seen_names:
                    seen_names.add(skill.name)
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

    # Resolve LLM provider for generation (skills LLM > global LLM)
    llm_provider = _resolve_generation_llm(session)
    engine = GenerationEngine(llm_provider=llm_provider, corpus_retriever=corpus_retriever)

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

    # Save to generation history
    from ..models import GenerationHistory
    history = GenerationHistory(
        user_id=current_user.id,
        team_id=team_id,
        skill_name=result.skill_name,
        skill_version=result.skill_version,
        input_text=body.input,
        output_content=result.content,
        citations=json.dumps(result.citations) if result.citations else None,
        generation_time_ms=result.generation_time_ms,
        metadata_json=json.dumps(result.metadata) if result.metadata else None,
    )
    session.add(history)
    session.commit()
    session.refresh(history)

    return {
        "id": history.id,
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


@router.delete("/{team_id}/skills/{skill_name}")
def delete_skill(
    team_id: int,
    skill_name: str,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Delete a team-specific skill (manager only)."""
    from ..models import Team, TeamRole
    membership = get_team_membership(team_id, current_user, session)
    if membership.team_role != TeamRole.manager:
        raise HTTPException(status_code=403, detail="Team manager role required")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Only allow deleting team-specific skills (not built-in)
    team_dir = SKILLS_DIR / team.slug
    if not team_dir.exists():
        raise HTTPException(status_code=404, detail="Skill not found")

    for f in team_dir.glob("*.md"):
        try:
            skill = SkillParser.parse_file(f)
            if skill.name == skill_name:
                f.unlink()
                return {"message": f"Skill '{skill_name}' deleted"}
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="Skill not found or is a built-in skill")


# ── Generation History ────────────────────────────────────────────────────────

@router.get("/{team_id}/generation-history")
def list_generation_history(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    limit: int = 50,
):
    """List generation history for a team."""
    from sqlmodel import select
    from ..models import GenerationHistory

    get_team_membership(team_id, current_user, session)

    rows = session.exec(
        select(GenerationHistory)
        .where(GenerationHistory.team_id == team_id)
        .order_by(GenerationHistory.created_at.desc())
        .limit(limit)
    ).all()

    return [
        {
            "id": r.id,
            "skill_name": r.skill_name,
            "skill_version": r.skill_version,
            "input_text": r.input_text[:200],
            "output_preview": r.output_content[:300],
            "generation_time_ms": r.generation_time_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{team_id}/generation-history/{history_id}")
def get_generation_detail(
    team_id: int,
    history_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Get full details of a generated document."""
    from ..models import GenerationHistory

    get_team_membership(team_id, current_user, session)

    record = session.get(GenerationHistory, history_id)
    if not record or record.team_id != team_id:
        raise HTTPException(status_code=404, detail="Record not found")

    return {
        "id": record.id,
        "skill_name": record.skill_name,
        "skill_version": record.skill_version,
        "input_text": record.input_text,
        "content": record.output_content,
        "citations": json.loads(record.citations) if record.citations else [],
        "generation_time_ms": record.generation_time_ms,
        "metadata": json.loads(record.metadata_json) if record.metadata_json else {},
        "created_at": record.created_at.isoformat(),
    }


@router.get("/{team_id}/generation-history/{history_id}/pdf")
def download_generation_pdf(
    team_id: int,
    history_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Download a generated document as PDF."""
    from ..models import GenerationHistory

    get_team_membership(team_id, current_user, session)

    record = session.get(GenerationHistory, history_id)
    if not record or record.team_id != team_id:
        raise HTTPException(status_code=404, detail="Record not found")

    pdf_bytes = _render_pdf(record.skill_name, record.input_text, record.output_content, record.created_at)

    filename = f"zettabrain-{record.skill_name.lower().replace(' ', '-')}-{record.id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render_pdf(skill_name: str, input_text: str, content: str, created_at) -> bytes:
    """Render generation output as a clean PDF using fpdf2."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    w = pdf.epw  # effective page width (page width minus margins)

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(w, 12, "ZettaBrain Platform", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(107, 114, 128)
    pdf.cell(w, 6, f"Generated Document - {skill_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w, 6, f"Date: {created_at.strftime('%Y-%m-%d %H:%M UTC')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Divider
    pdf.set_draw_color(229, 231, 235)
    pdf.line(15, pdf.get_y(), 15 + w, pdf.get_y())
    pdf.ln(8)

    # Input section
    pdf.set_text_color(55, 65, 81)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(w, 8, "Request:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(75, 85, 99)
    pdf.multi_cell(w, 5, input_text[:500])
    pdf.ln(6)

    # Content section
    pdf.set_text_color(17, 24, 39)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(w, 8, "Generated Content:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(31, 41, 55)

    # Handle content line by line for proper wrapping
    for line in content.split("\n"):
        # Reset X to left margin before each line
        pdf.set_x(pdf.l_margin)

        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.ln(4)
            pdf.multi_cell(w, 7, line[2:])
            pdf.set_font("Helvetica", "", 10)
        elif line.startswith("## "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(3)
            pdf.multi_cell(w, 6, line[3:])
            pdf.set_font("Helvetica", "", 10)
        elif line.startswith("### "):
            pdf.set_font("Helvetica", "B", 11)
            pdf.ln(2)
            pdf.multi_cell(w, 6, line[4:])
            pdf.set_font("Helvetica", "", 10)
        elif line.startswith("- ") or line.startswith("* "):
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(w - 5, 5, f"• {line[2:]}")
        elif line.strip() == "":
            pdf.ln(3)
        else:
            pdf.multi_cell(w, 5, line)

    # Footer
    pdf.ln(10)
    pdf.set_x(pdf.l_margin)
    pdf.set_draw_color(229, 231, 235)
    pdf.line(15, pdf.get_y(), 15 + w, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(w, 5, "Generated by ZettaBrain Platform", new_x="LMARGIN", new_y="NEXT")

    return pdf.output()


def _resolve_generation_llm(session):
    """Resolve the LLM provider for skills/generation.

    Priority: skills-specific LLM settings > global LLM settings.
    Uses the same API keys stored in system config.
    """
    from ..llm.factory import create_generation_provider
    from .settings import get_setting

    # Check if skills has its own LLM configured
    skills_provider = get_setting(session, "skills_llm_provider")
    skills_model = get_setting(session, "skills_llm_model")
    skills_api_key = get_setting(session, "skills_llm_api_key")

    if skills_provider:
        provider_name = skills_provider
        model = skills_model or None
        api_key = skills_api_key or None
    else:
        # Fall back to global LLM settings
        provider_name = get_setting(session, "llm_provider") or "ollama"
        model = None
        api_key = None

    # Resolve the model name from provider-specific settings if not explicit
    if not model:
        if provider_name == "ollama":
            model = get_setting(session, "llm_model") or "llama3.1:8b"
        elif provider_name == "openai":
            model = get_setting(session, "openai_llm_model") or "gpt-4o"
        elif provider_name == "claude":
            model = get_setting(session, "claude_llm_model") or "claude-sonnet-4-6"
        elif provider_name == "groq":
            model = get_setting(session, "groq_llm_model") or "llama-3.1-8b-instant"
        elif provider_name == "together":
            model = get_setting(session, "together_llm_model") or "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
        elif provider_name == "cerebras":
            model = get_setting(session, "cerebras_llm_model") or "llama3.1-8b"
        elif provider_name == "openrouter":
            model = get_setting(session, "openrouter_llm_model") or "meta-llama/llama-3.1-8b-instruct:free"
        elif provider_name == "fireworks":
            model = get_setting(session, "fireworks_llm_model") or "accounts/fireworks/models/llama-v3p1-8b-instruct"

    # Resolve API key from system config if not explicitly set for skills
    if not api_key:
        if provider_name == "openai":
            api_key = get_setting(session, "openai_api_key")
        elif provider_name == "claude":
            api_key = get_setting(session, "anthropic_api_key")
        elif provider_name == "groq":
            api_key = get_setting(session, "groq_api_key")
        elif provider_name == "together":
            api_key = get_setting(session, "together_api_key")
        elif provider_name == "cerebras":
            api_key = get_setting(session, "cerebras_api_key")
        elif provider_name == "openrouter":
            api_key = get_setting(session, "openrouter_api_key")
        elif provider_name == "fireworks":
            api_key = get_setting(session, "fireworks_api_key")

    # Build kwargs
    kwargs = {}
    if provider_name == "ollama":
        base_url = get_setting(session, "ollama_host") or "http://localhost:11434"
        kwargs["base_url"] = base_url

    return create_generation_provider(
        provider_name=provider_name,
        model=model,
        api_key=api_key if api_key else None,
        **kwargs,
    )


def _find_skill_file(skill_name: str, team_slug: str) -> Optional[Path]:
    """Find a skill file by name, checking team-specific first, then global, then built-in."""
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

    # Check global skills in data directory
    if SKILLS_DIR.exists():
        for f in SKILLS_DIR.glob("*.md"):
            try:
                skill = SkillParser.parse_file(f)
                if skill.name == skill_name:
                    return f
            except Exception:
                continue

    # Check built-in skills shipped with package
    if _BUILTIN_SKILLS_DIR.exists():
        for f in _BUILTIN_SKILLS_DIR.glob("*.md"):
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
