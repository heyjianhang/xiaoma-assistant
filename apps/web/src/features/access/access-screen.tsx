"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LoaderCircleIcon, KeyRoundIcon } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { loginProof } from "@/lib/access/client";
import { useAccess } from "@/lib/access/provider";

export function AccessScreen() {
  const pathname = usePathname(); const router = useRouter(); const { refresh, user } = useAccess();
  const [admin, setAdmin] = useState(pathname.startsWith("/admin") || pathname.startsWith("/agents"));
  const [token, setToken] = useState(""); const [password, setPassword] = useState("");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const value = params.get("invite");
    if (value) { queueMicrotask(() => { setToken(value); setAdmin(false); }); }
  }, []);
  async function submit() {
    setBusy(true); setError("");
    try {
      const credential = admin ? password : token;
      const proof = await loginProof(credential);
      const response = await fetch(admin ? "/api/v1/auth/admin-login" : "/api/v1/auth/redeem", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...proof, ...(admin ? { password } : { token }) }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message ?? body.detail ?? "无法登录");
      history.replaceState(null, "", window.location.pathname);
      setPassword(""); setToken(""); await refresh(); router.replace(admin ? pathname.startsWith("/agents") ? "/agents" : "/admin" : "/chat");
    } catch (error) { setError(error instanceof Error ? error.message : "无法登录，请重试。"); }
    finally { setBusy(false); }
  }
  return <main className="grid min-h-svh place-items-center bg-muted/30 p-6"><div className="flex w-full max-w-sm flex-col gap-6 rounded-2xl border bg-background p-7 shadow-sm">
    <div className="flex items-center gap-3"><BrandMark className="size-9" /><h1 className="text-xl font-semibold">小马助手</h1></div>
    {user && <Button variant="outline" onClick={() => router.replace("/chat")}>返回工作台</Button>}
    <form className="flex flex-col gap-5" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <FieldGroup><Field><FieldLabel htmlFor="access-credential">{admin ? "管理员密码" : "邀请凭据"}</FieldLabel><Input id="access-credential" type="password" autoComplete={admin ? "current-password" : "off"} value={admin ? password : token} onChange={event => admin ? setPassword(event.target.value) : setToken(event.target.value)} placeholder={admin ? "输入管理员密码" : "请打开管理员发给你的邀请链接"} disabled={busy} /></Field></FieldGroup>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <Button disabled={busy || !(admin ? password : token)} type="submit">{busy ? <LoaderCircleIcon data-icon="inline-start" className="animate-spin" /> : <KeyRoundIcon data-icon="inline-start" />}{admin ? "登录管理后台" : "绑定本设备并进入"}</Button>
    </form>
    <Button variant="ghost" size="sm" disabled={busy} onClick={() => { setAdmin(value => !value); setError(""); }}>{admin ? "使用邀请链接访问" : "管理员登录"}</Button>
  </div></main>;
}
