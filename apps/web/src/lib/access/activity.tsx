"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { authFetch, jsonRequest } from "./client";

type ActivityKind = "page_view" | "document_view" | "sql_view" | "test_case_view";
interface ActivityTarget { path?: string; tab?: string; document_id?: string; target_id?: string }
const recent = new Map<string, number>();
let trackingIdentity: string | undefined;

export function trackActivity(kind: ActivityKind, target: ActivityTarget = {}) {
  const path = target.path ?? window.location.pathname;
  if (path === "/access" || document.visibilityState === "hidden") return;
  const body = { kind, ...target, path };
  const key = JSON.stringify(body);
  const now = Date.now();
  if (now - (recent.get(key) ?? 0) < 2000) return;
  for (const [key, stamp] of recent) if (now - stamp > 2000) recent.delete(key);
  recent.set(key, now);
  const request = { ...body, event_id: crypto.randomUUID() };
  // Best effort, signed and idempotent. A retry uses the same event ID.
  void (async () => {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const response = await authFetch("/api/v1/activity/events", { ...jsonRequest("POST", request), keepalive: true });
        if (response.ok || response.status < 500) return;
      } catch { /* Navigation must remain usable if activity logging is unavailable. */ }
    }
  })();
}

export function useActivityView(kind: ActivityKind, target: ActivityTarget, enabled = true) {
  const { path, tab, document_id, target_id } = target;
  useEffect(() => {
    const record = () => { if (enabled) trackActivity(kind, { path, tab, document_id, target_id }); };
    record();
    document.addEventListener("visibilitychange", record);
    return () => document.removeEventListener("visibilitychange", record);
  }, [kind, path, tab, document_id, target_id, enabled]);
}

export function ActivityTracker({ userId }: { userId: string }) {
  const pathname = usePathname();
  useEffect(() => {
    if (trackingIdentity !== userId) { recent.clear(); trackingIdentity = userId; }
  }, [userId]);
  // Project tabs record their own visible section instead of a duplicate page event.
  useActivityView("page_view", { path: pathname }, pathname !== "/project");
  return null;
}
