"use client";

let keyPromise: Promise<CryptoKeyPair> | undefined;
const bytes64 = (bytes: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
async function hex(bytes: ArrayBuffer) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(value => value.toString(16).padStart(2, "0")).join("");
}
export function deviceKey(): Promise<CryptoKeyPair> {
  if (keyPromise) return keyPromise;
  keyPromise = (async () => {
    if (!window.isSecureContext || !crypto.subtle) throw new Error("设备认证需要 HTTPS 或 localhost 安全连接。");
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("xiaoma-device", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("keys");
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
    });
    try {
      const stored = await new Promise<CryptoKeyPair | undefined>((resolve, reject) => {
        const request = database.transaction("keys").objectStore("keys").get("device");
        request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
      });
      if (stored) return stored;
      const keys = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign", "verify"]);
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction("keys", "readwrite");
        transaction.objectStore("keys").put(keys, "device");
        transaction.oncomplete = () => resolve(); transaction.onerror = () => reject(transaction.error);
      });
      return keys;
    } finally { database.close(); }
  })();
  return keyPromise;
}
async function sign(value: string) {
  const keys = await deviceKey();
  return bytes64(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, keys.privateKey, new TextEncoder().encode(value)));
}
export async function loginProof(credential: string) {
  const response = await fetch("/api/v1/auth/challenge", { cache: "no-store" });
  if (!response.ok) throw new Error("无法获取登录验证，请稍后重试。");
  const { challenge } = await response.json();
  const keys = await deviceKey();
  return { challenge, public_key: await crypto.subtle.exportKey("jwk", keys.publicKey),
    signature: await sign(`xiaoma-login\n${challenge}\n${await hex(new TextEncoder().encode(credential).buffer)}`) };
}
export async function authFetch(input: string, init: RequestInit = {}) {
  const request = new Request(new URL(input, window.location.origin), { ...init, credentials: "same-origin" });
  const body = await request.clone().arrayBuffer();
  const timestamp = String(Math.floor(Date.now() / 1000)); const nonce = crypto.randomUUID();
  const url = new URL(request.url);
  const proof = await sign(`${request.method}\n${url.pathname}${url.search}\n${timestamp}\n${nonce}\n${await hex(body)}`);
  request.headers.set("X-Device-Time", timestamp); request.headers.set("X-Device-Nonce", nonce); request.headers.set("X-Device-Proof", proof);
  const response = await fetch(request);
  if (response.status === 401) window.dispatchEvent(new Event("xiaoma-auth-invalid"));
  else if (response.status === 403 && !url.pathname.startsWith("/api/v1/admin/")) {
    const body = await response.clone().json().catch(() => null);
    if (/邀请|绑定|登录|设备/.test(body?.message ?? "")) window.dispatchEvent(new Event("xiaoma-auth-invalid"));
  }
  return response;
}
export async function accessApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`/api/v1${path}`, { cache: "no-store", ...init });
  const body = await response.json();
  if (!response.ok) throw new Error(body.message ?? body.detail ?? "请求失败，请重试。");
  return body as T;
}
export const jsonRequest = (method: string, value: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
