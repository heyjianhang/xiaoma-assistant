"""Independent CLI device identity; no database or authentication bypass."""

import base64
import hashlib
import ipaddress
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


class CliError(Exception):
    pass


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def secure_directory(path: Path):
    if path.is_symlink():
        raise CliError("调试目录不能是符号链接")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def private_write(path: Path, value: str):
    secure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def private_json(path: Path, value):
    private_write(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def origin_url(value):
    url = urlsplit(value)
    try:
        port = url.port
    except ValueError as exc:
        raise CliError("服务地址的端口无效") from exc
    try:
        local = url.hostname == "localhost" or ipaddress.ip_address(url.hostname or "").is_loopback
    except ValueError:
        local = url.hostname == "localhost"
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or (url.scheme == "http" and not local)
    ):
        raise CliError("服务地址须为 HTTPS origin；仅 localhost / 回环地址允许 HTTP")
    host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
    default_port = 443 if url.scheme == "https" else 80
    return f"{url.scheme}://{host}" + (f":{port}" if port and port != default_port else "")


class DebugClient:
    def __init__(self, url, state_dir: Path, *, transport=None):
        self.origin = origin_url(url)
        self.state_file = state_dir / (
            hashlib.sha256(self.origin.encode()).hexdigest()[:20] + ".json"
        )
        secure_directory(state_dir)
        if self.state_file.is_symlink():
            raise CliError("身份文件不能是符号链接")
        state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
        if state and state.get("origin") != self.origin:
            raise CliError("身份文件的服务地址不匹配")
        self.key = (
            serialization.load_pem_private_key(state["private_key"].encode(), None)
            if state
            else ec.generate_private_key(ec.SECP256R1())
        )
        self.http = httpx.Client(
            base_url=self.origin,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(15, read=45),
        )
        if state.get("session"):
            self.http.cookies.set("xiaoma_session", state["session"])

    def save(self):
        private_json(
            self.state_file,
            {
                "origin": self.origin,
                "private_key": self.key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ).decode(),
                "session": self.http.cookies.get("xiaoma_session"),
            },
        )

    def signature(self, value):
        der = self.key.sign(value.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    def login(self, password):
        challenge = self.request("GET", "/api/v1/auth/challenge", signed=False)["challenge"]
        numbers = self.key.public_key().public_numbers()
        body = {
            "challenge": challenge,
            "public_key": {
                "kty": "EC",
                "crv": "P-256",
                "x": b64(numbers.x.to_bytes(32, "big")),
                "y": b64(numbers.y.to_bytes(32, "big")),
            },
            "signature": self.signature(
                f"xiaoma-login\n{challenge}\n{hashlib.sha256(password.encode()).hexdigest()}"
            ),
            "password": password,
        }
        self.http.cookies.clear()
        self.request("POST", "/api/v1/auth/admin-login", body, signed=False)
        self.save()
        return self.request("GET", "/api/v1/auth/me")

    def build(self, method, path, value=None, *, signed=True):
        if not path.startswith("/api/") or path.startswith("//"):
            raise CliError("只允许调用当前服务的 API 路径")
        body = (
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            if value is not None
            else b""
        )
        request = self.http.build_request(method, path, content=body)
        request.headers["Content-Type"] = "application/json"
        if signed:
            stamp, nonce = str(int(time.time())), str(uuid4())
            target = request.url.raw_path.decode("ascii")
            request.headers.update(
                {
                    "X-Device-Time": stamp,
                    "X-Device-Nonce": nonce,
                    "X-Device-Proof": self.signature(
                        f"{method}\n{target}\n{stamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
                    ),
                }
            )
        return request

    @staticmethod
    def check(response):
        if response.is_success:
            return
        # Never echo raw proxy/provider responses, cookies or login request bodies.
        if response.status_code in (401, 403):
            raise CliError(
                f"访问被拒绝（HTTP {response.status_code}），请重新 login 或核对身份权限"
            )
        try:
            detail = response.json().get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        raise CliError(f"HTTP {response.status_code}: {detail or '服务请求失败'}")

    def request(self, method, path, value=None, *, signed=True):
        response = self.http.send(self.build(method, path, value, signed=signed))
        self.check(response)
        return response.json()

    def close(self):
        self.http.close()
