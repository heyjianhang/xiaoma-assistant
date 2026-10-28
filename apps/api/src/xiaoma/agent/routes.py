from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


class ToolAccess(BaseModel):
    knowledge: bool = True
    data: bool = True


class ChatRequest(BaseModel):
    conversation_id: UUID
    question: str = Field(min_length=1, max_length=4000)
    model_id: str | None = Field(default=None, max_length=160)
    tools: ToolAccess = Field(default_factory=ToolAccess)
    skills: list[str] = Field(default_factory=list, max_length=5)
    request_id: UUID | None = None


def router(holder):
    r = APIRouter(prefix="/api/v1")

    @r.get("/agent/models", tags=["Agent"])
    async def models():
        items = await holder["models"].list()
        return {"items": items, "default": items[0]["id"]}

    @r.get("/agent/skills", tags=["Agent"])
    async def skills():
        from .tools import OUTPUT_NAMES, SQL_TOOL_NAMES

        names = (
            SQL_TOOL_NAMES
            | OUTPUT_NAMES
            | {"load_skill", "read_skill_resource", "search_knowledge", "write_todos"}
        )
        items = await holder["agents"].active_skills(names)
        return {
            "items": [
                {
                    **{
                        k: s[k] for k in ("id", "name", "description", "required_tools", "revision")
                    },
                    "source": (s.get("manifest") or {}).get("source", "builtin"),
                }
                for s in items
            ]
        }

    @r.get("/conversations", tags=["对话"])
    async def conversations(request: Request):
        return {"items": await holder["agents"].list_conversations(request.state.principal.user_id)}

    @r.delete("/conversations/{id}", tags=["对话"])
    async def remove(id: UUID, request: Request):
        await holder["agents"].remove(request.state.principal.user_id, id)
        return {"ok": True}

    @r.post("/conversations/{id}/restore", tags=["对话"])
    async def restore(id: UUID, request: Request):
        await holder["agents"].remove(request.state.principal.user_id, id, restore=True)
        return {"ok": True}

    @r.post("/agent/serve", tags=["Agent"])
    async def serve(body: ChatRequest, request: Request):
        service = holder["background_runs"]
        principal = request.state.principal
        created = await service.submit(principal, body)
        return StreamingResponse(
            service.stream(principal, UUID(created["run_id"])),
            media_type="text/event-stream",
            # Next.js compression respects no-transform. Gzip otherwise buffers
            # these small SSE frames until the stream finishes.
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )

    @r.post("/agent/runs", status_code=202, tags=["Agent"])
    async def create_run(body: ChatRequest, request: Request):
        return await holder["background_runs"].submit(request.state.principal, body)

    @r.get("/agent/runs/{id}", tags=["Agent"])
    async def get_run(id: UUID, request: Request):
        return await holder["background_runs"].describe(request.state.principal.user_id, id)

    @r.get("/agent/runs/{id}/events", tags=["Agent"])
    async def events(id: UUID, request: Request, after: int = Query(0, ge=0)):
        service = holder["background_runs"]
        info = await service.describe(request.state.principal.user_id, id)
        if after > info["event_sequence"]:
            raise HTTPException(422, "事件游标超出当前运行范围")
        return StreamingResponse(
            service.stream(request.state.principal, id, after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )

    @r.post("/agent/runs/{id}/stop", tags=["Agent"])
    async def stop(id: UUID, request: Request):
        return await holder["background_runs"].cancel(request.state.principal.user_id, id)

    @r.get("/admin/debug/runs/{id}", tags=["调试"])
    async def debug_run(id: UUID, request: Request):
        principal = request.state.principal
        if principal.role != "admin":
            raise HTTPException(403, "仅管理员可调试")
        return await holder["agents"].debug_run(principal.user_id, id)

    @r.get("/admin/debug/conversations/{id}", tags=["调试"])
    async def debug_conversation(id: UUID, request: Request):
        principal = request.state.principal
        if principal.role != "admin":
            raise HTTPException(403, "仅管理员可调试")
        return await holder["agents"].debug_conversation(principal.user_id, id)

    return r
