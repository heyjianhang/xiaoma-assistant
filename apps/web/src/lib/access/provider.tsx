"use client";
import { createContext, useContext, useEffect, useState, useRef, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { accessApi } from "./client";
import { AccessScreen } from "@/features/access/access-screen";
import { Skeleton } from "@/components/ui/skeleton";

export interface AccessUser { id: string; name: string; role: "admin" | "guest" }
const Context = createContext<{ user: AccessUser | null; refresh: () => Promise<void>; logout: () => Promise<void> } | null>(null);
export function AccessProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AccessUser | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();
  const generation = useRef(0);
  async function refresh() {
    const run = ++generation.current;
    try { const value = await accessApi<AccessUser>("/auth/me"); if (run === generation.current) setUser(value); }
    catch { if (run === generation.current) setUser(null); }
    finally { setLoading(false); }
  }
  async function logout() { ++generation.current; try { await accessApi("/auth/logout", { method: "POST" }); } finally { setUser(null); } }
  useEffect(() => {
    void Promise.resolve().then(refresh);
    const invalid = () => { ++generation.current; setUser(null); };
    window.addEventListener("xiaoma-auth-invalid", invalid);
    const timer = setInterval(() => { void refresh(); }, 30000);
    return () => { clearInterval(timer); window.removeEventListener("xiaoma-auth-invalid", invalid); };
  }, []);
  return <Context.Provider value={{ user, refresh, logout }}>{loading ? <div className="grid min-h-svh place-items-center"><Skeleton className="h-48 w-80" /></div> : !user || pathname === "/access" ? <AccessScreen /> : <div key={user.id} className="contents">{children}</div>}</Context.Provider>;
}
export function useAccess() { const value = useContext(Context); if (!value) throw new Error("AccessProvider is required"); return value; }
