"""Reasoning presentation state, independent from answer text and tool state."""

from datetime import UTC, datetime


def apply_reasoning_event(payload, event):
    parts = {p["id"]: p for p in payload.get("reasoning", [])}
    part = dict(parts.get(event["id"], {"id": event["id"], "content": "", "state": "streaming"}))
    part["content"] += event.get("text", "")
    for key in ("state", "durationMs", "startedAt"):
        if key in event:
            part[key] = event[key]
    parts[event["id"]] = part
    payload["reasoning"] = list(parts.values())


def close_reasoning(payload, state):
    for part in payload.get("reasoning", []):
        if part["state"] == "streaming":
            part["state"] = state
            if part.get("startedAt"):
                start = datetime.fromisoformat(part["startedAt"])
                part["durationMs"] = max(
                    0, round((datetime.now(UTC) - start).total_seconds() * 1000)
                )
