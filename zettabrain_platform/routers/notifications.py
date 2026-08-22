"""Real-time notifications via Server-Sent Events (SSE)."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlmodel import select

from ..deps import SessionDep
from ..models import ModelRequest, Team

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

_active_connections: dict[int, list[asyncio.Queue]] = {}


def broadcast_to_user(user_id: int, event: dict):
    if user_id not in _active_connections:
        return
    for queue in _active_connections[user_id]:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


def notify_request_reviewed(request: ModelRequest, session):
    requester_id = request.requester_id
    team = session.get(Team, request.team_id)
    team_name = team.name if team else f"Team #{request.team_id}"

    event = {
        "type": "model_request_reviewed",
        "request_id": request.id,
        "team_id": request.team_id,
        "team_name": team_name,
        "status": request.status,
        "rejection_reason": request.rejection_reason,
        "llm_provider": request.llm_provider,
        "llm_model": request.llm_model,
        "embed_provider": request.embed_provider,
        "embed_model": request.embed_model,
    }
    broadcast_to_user(requester_id, event)


def notify_new_request(request: ModelRequest, session):
    from ..models import User, SystemRole

    admins = session.exec(
        select(User).where(User.system_role == SystemRole.admin)
    ).all()

    team = session.get(Team, request.team_id)
    team_name = team.name if team else f"Team #{request.team_id}"

    event = {
        "type": "new_model_request",
        "request_id": request.id,
        "team_id": request.team_id,
        "team_name": team_name,
    }

    for admin in admins:
        broadcast_to_user(admin.id, event)


async def event_stream(user_id: int) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    if user_id not in _active_connections:
        _active_connections[user_id] = []
    _active_connections[user_id].append(queue)

    try:
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    except asyncio.CancelledError:
        pass
    finally:
        if user_id in _active_connections:
            _active_connections[user_id].remove(queue)
            if not _active_connections[user_id]:
                del _active_connections[user_id]


@router.get("/stream")
async def notification_stream(
    token: str,
    session: SessionDep,
) -> StreamingResponse:
    from fastapi import HTTPException, status
    from ..auth import decode_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        from ..models import User
        user = session.get(User, int(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user")
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"SSE authentication failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {str(e)}")

    return StreamingResponse(
        event_stream(user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
