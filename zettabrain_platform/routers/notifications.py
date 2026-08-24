"""
Real-time notifications via Server-Sent Events (SSE)
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import select

from ..deps import CurrentUser, SessionDep
from ..models import ModelRequest, ModelRequestStatus, Team, TeamMember, TeamRole

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# Store active SSE connections
# Format: {user_id: [queues]}
_active_connections: dict[int, list[asyncio.Queue]] = {}


def broadcast_to_user(user_id: int, event: dict):
    """
    Broadcast an event to all active connections for a user.

    Args:
        user_id: User to notify
        event: Event data to send
    """
    if user_id not in _active_connections:
        return

    # Send to all active connections for this user
    for queue in _active_connections[user_id]:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Queue full, skip this event


def notify_request_reviewed(request: ModelRequest, session):
    """
    Called when a model request is approved/rejected.
    Notifies the requester.

    Args:
        request: The reviewed model request
        session: Database session
    """
    # Get the requester
    requester_id = request.requester_id

    # Get team name
    team = session.get(Team, request.team_id)
    team_name = team.name if team else f"Team #{request.team_id}"

    # Build event
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

    # Broadcast to requester
    broadcast_to_user(requester_id, event)


def notify_new_request(request: ModelRequest, session):
    """
    Called when a new model request is submitted.
    Notifies all admins.

    Args:
        request: The new model request
        session: Database session
    """
    from ..models import User, SystemRole

    # Get all admin users
    admins = session.exec(
        select(User).where(User.system_role == SystemRole.admin)
    ).all()

    # Get team name
    team = session.get(Team, request.team_id)
    team_name = team.name if team else f"Team #{request.team_id}"

    # Build event
    event = {
        "type": "new_model_request",
        "request_id": request.id,
        "team_id": request.team_id,
        "team_name": team_name,
    }

    # Broadcast to all admins
    for admin in admins:
        broadcast_to_user(admin.id, event)


async def event_stream(user_id: int) -> AsyncGenerator[str, None]:
    """
    SSE event stream for a user.

    Yields SSE-formatted messages.
    """
    # Create queue for this connection
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    # Register connection
    if user_id not in _active_connections:
        _active_connections[user_id] = []
    _active_connections[user_id].append(queue)

    try:
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        # Send keepalive every 30 seconds to prevent timeout
        while True:
            try:
                # Wait for event with timeout
                event = await asyncio.wait_for(queue.get(), timeout=30.0)

                # Send event to client
                yield f"data: {json.dumps(event)}\n\n"

            except asyncio.TimeoutError:
                # Send keepalive
                yield f": keepalive\n\n"

    except asyncio.CancelledError:
        # Connection closed
        pass
    finally:
        # Unregister connection
        if user_id in _active_connections:
            _active_connections[user_id].remove(queue)
            if not _active_connections[user_id]:
                del _active_connections[user_id]


@router.get("/stream")
async def notification_stream(
    token: str,
    session: SessionDep,
) -> StreamingResponse:
    """
    SSE endpoint for real-time notifications.

    Token is passed as query parameter because EventSource doesn't support custom headers.

    Returns:
        StreamingResponse with SSE events
    """
    from fastapi import HTTPException, status
    from ..auth import decode_token

    # Validate token is provided
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")

    # Authenticate using token from query parameter
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
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
