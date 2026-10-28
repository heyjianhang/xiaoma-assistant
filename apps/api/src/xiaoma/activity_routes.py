import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime

from .activity import ActivityInput

logger = logging.getLogger(__name__)


async def record_login(holder, token, request, *, activated=False):
    # A telemetry outage must not prevent a successful authenticated login.
    try:
        await asyncio.wait_for(
            holder["activity"].login(
                token, request.headers.get("user-agent", ""), activated=activated
            ),
            timeout=2,
        )
    except Exception:
        logger.warning("Login activity could not be recorded")


def router(holder):
    r = APIRouter(prefix="/api/v1")

    @r.post("/activity/events", tags=["访问记录"])
    async def record(body: ActivityInput, request: Request):
        await holder["auth"].rate_limit(str(request.state.principal.user_id), "activity", 120)
        return await holder["activity"].record(
            request.state.principal, body, request.headers.get("user-agent", "")
        )

    @r.get("/admin/activity", tags=["访问记录"])
    async def events(
        request: Request,
        invite_id: UUID | None = None,
        kind: str | None = None,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
        offset: int = Query(0, ge=0, le=100000),
        limit: int = Query(30, ge=1, le=100),
    ):
        if request.state.principal.role != "admin":
            raise HTTPException(403, "仅管理员可以查看访问记录")
        return await holder["activity"].list_events(invite_id, kind, start, end, offset, limit)

    return r
