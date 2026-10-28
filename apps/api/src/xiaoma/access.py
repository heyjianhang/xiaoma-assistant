"""Invitation access, expiring sessions, and per-request browser-key proof of possession."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import HTTPException
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from .database import utcnow

COOKIE = "xiaoma_session"
ADMIN_ID = uuid5(NAMESPACE_URL, "xiaoma-assistant:administrator")


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def decode64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def public_key(jwk):
    if not isinstance(jwk, dict) or set(jwk) - {"kty", "crv", "x", "y", "ext", "key_ops"}:
        raise ValueError("Invalid public key")
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("Only P-256 public keys are accepted")
    return ec.EllipticCurvePublicNumbers(
        int.from_bytes(decode64(jwk["x"]), "big"),
        int.from_bytes(decode64(jwk["y"]), "big"),
        ec.SECP256R1(),
    ).public_key()


def key_fingerprint(jwk):
    public_key(jwk)
    return digest(json.dumps({k: jwk[k] for k in ("kty", "crv", "x", "y")}, sort_keys=True))


def verify(jwk, signature: str, message: str):
    raw = decode64(signature)
    if len(raw) != 64:
        raise ValueError("Invalid signature")
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    public_key(jwk).verify(der, message.encode(), ec.ECDSA(hashes.SHA256()))


def password_hash(password: str, salt: bytes | None = None):
    salt = salt or secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    return f"scrypt${salt.hex()}${value}"


def password_matches(password, encoded):
    try:
        _, salt, value = encoded.split("$")
        return hmac.compare_digest(
            password_hash(password, bytes.fromhex(salt)).split("$")[-1], value
        )
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    session_id: UUID
    role: str
    name: str


class AccessStore:
    def __init__(self, db):
        self.db = db
        self.cleanup_after = 0.0
        m = db.metadata
        schema = db.schema
        self.users = Table(
            "access_users",
            m,
            Column("id", PGUUID(as_uuid=True), primary_key=True),
            Column("name", String(80), nullable=False),
            Column("role", String(10), nullable=False),
            Column("invite_id", PGUUID(as_uuid=True)),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self.invites = Table(
            "access_invites",
            m,
            Column("id", PGUUID(as_uuid=True), primary_key=True),
            Column("name", String(80), nullable=False),
            Column("token_hash", String(64), unique=True, nullable=False),
            Column("valid_from", DateTime(timezone=True), nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False),
            Column("revoked_at", DateTime(timezone=True)),
            Column("bound_key", String(64)),
            Column("bound_user_id", PGUUID(as_uuid=True)),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self.sessions = Table(
            "access_sessions",
            m,
            Column("id", PGUUID(as_uuid=True), primary_key=True),
            Column("token_hash", String(64), unique=True, nullable=False),
            Column(
                "user_id",
                PGUUID(as_uuid=True),
                ForeignKey(f"{schema}.access_users.id"),
                nullable=False,
            ),
            Column("public_key", JSONB, nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False),
            Column("revoked_at", DateTime(timezone=True)),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self.challenges = Table(
            "access_challenges",
            m,
            Column("id", String(64), primary_key=True),
            Column("expires_at", DateTime(timezone=True), nullable=False),
        )
        self.nonces = Table(
            "access_nonces",
            m,
            Column("session_id", PGUUID(as_uuid=True), primary_key=True),
            Column("nonce", String(64), primary_key=True),
            Column("expires_at", DateTime(timezone=True), nullable=False),
        )
        self.rates = Table(
            "access_rates",
            m,
            Column("key", String(64), primary_key=True),
            Column("count", Integer, nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False),
        )

    async def bootstrap(self):
        async with self.db.engine.begin() as c:
            await c.execute(
                insert(self.users)
                .values(id=ADMIN_ID, name="管理员", role="admin", created_at=utcnow())
                .on_conflict_do_nothing()
            )
            # Recover abandoned stream leases without touching currently active runs.
            await c.execute(delete(self.challenges).where(self.challenges.c.expires_at < utcnow()))
            await c.execute(delete(self.nonces).where(self.nonces.c.expires_at < utcnow()))
            await c.execute(delete(self.rates).where(self.rates.c.expires_at < utcnow()))

    async def rate_limit(self, ip: str, action: str, limit: int):
        key = digest(f"{ip}:{action}")
        now = utcnow()
        async with self.db.engine.begin() as c:
            stmt = insert(self.rates).values(
                key=key, count=1, expires_at=now + timedelta(minutes=1)
            )
            from sqlalchemy import case

            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "count": case((self.rates.c.expires_at < now, 1), else_=self.rates.c.count + 1),
                    "expires_at": case(
                        (self.rates.c.expires_at < now, now + timedelta(minutes=1)),
                        else_=self.rates.c.expires_at,
                    ),
                },
            ).returning(self.rates.c.count)
            count = (await c.execute(stmt)).scalar_one()
        if count > limit:
            raise HTTPException(429, "尝试过于频繁，请稍后再试")

    async def cleanup(self, conn):
        now = time.monotonic()
        if now < self.cleanup_after:
            return
        self.cleanup_after = now + 60
        for table in (self.challenges, self.nonces, self.rates, self.sessions):
            await conn.execute(delete(table).where(table.c.expires_at < utcnow()))

    async def challenge(self):
        value = secrets.token_urlsafe(24)
        async with self.db.engine.begin() as c:
            await self.cleanup(c)
            await c.execute(
                self.challenges.insert().values(
                    id=value, expires_at=utcnow() + timedelta(minutes=2)
                )
            )
        return value

    async def prove_login(self, challenge, jwk, signature, credential):
        try:
            verify(jwk, signature, f"xiaoma-login\n{challenge}\n{digest(credential)}")
        except Exception as exc:
            raise HTTPException(401, "设备验证失败") from exc
        async with self.db.engine.begin() as c:
            used = await c.execute(
                delete(self.challenges)
                .where(self.challenges.c.id == challenge, self.challenges.c.expires_at > utcnow())
                .returning(self.challenges.c.id)
            )
            if not used.first():
                raise HTTPException(401, "验证已失效，请重试")

    async def issue_session(self, conn, user_id, jwk, expires):
        token = secrets.token_urlsafe(32)
        await conn.execute(
            self.sessions.insert().values(
                id=uuid4(),
                user_id=user_id,
                token_hash=digest(token),
                public_key=jwk,
                expires_at=expires,
                created_at=utcnow(),
            )
        )
        return token

    async def admin_login(self, password, jwk):
        if not password_matches(password, self.db.settings.admin_password_hash.get_secret_value()):
            raise HTTPException(401, "管理员密码不正确")
        async with self.db.engine.begin() as c:
            return await self.issue_session(
                c, ADMIN_ID, jwk, utcnow() + timedelta(hours=self.db.settings.session_hours)
            )

    @staticmethod
    def check_invite(row, now=None):
        now = now or utcnow()
        if row["revoked_at"] is not None:
            raise HTTPException(403, "邀请已撤销")
        if now < row["valid_from"]:
            raise HTTPException(403, "邀请尚未生效")
        if now >= row["expires_at"]:
            raise HTTPException(403, "邀请已到期")

    async def redeem(self, token, jwk, *, with_activation=False):
        fingerprint = key_fingerprint(jwk)
        async with self.db.engine.begin() as c:
            invite = (
                (
                    await c.execute(
                        select(self.invites)
                        .where(self.invites.c.token_hash == digest(token))
                        .with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if not invite:
                raise HTTPException(403, "邀请链接无效")
            self.check_invite(invite)
            if invite["bound_key"] and not hmac.compare_digest(invite["bound_key"], fingerprint):
                raise HTTPException(403, "邀请已绑定其他浏览器设备，请联系管理员重置")
            user_id = invite["bound_user_id"] or uuid4()
            if not invite["bound_user_id"]:
                await c.execute(
                    self.users.insert().values(
                        id=user_id,
                        name=invite["name"],
                        role="guest",
                        invite_id=invite["id"],
                        created_at=utcnow(),
                    )
                )
                await c.execute(
                    self.invites.update()
                    .where(self.invites.c.id == invite["id"])
                    .values(bound_key=fingerprint, bound_user_id=user_id)
                )
            session_token = await self.issue_session(
                c,
                user_id,
                jwk,
                min(
                    invite["expires_at"], utcnow() + timedelta(hours=self.db.settings.session_hours)
                ),
            )
            return (
                (session_token, not bool(invite["bound_user_id"]))
                if with_activation
                else session_token
            )

    async def session(self, session_id=None, token=None):
        s, u = self.sessions, self.users
        condition = s.c.id == session_id if session_id else s.c.token_hash == digest(token or "")
        async with self.db.engine.connect() as c:
            row = (
                (
                    await c.execute(
                        select(s, u.c.name, u.c.role, u.c.invite_id)
                        .join(u, u.c.id == s.c.user_id)
                        .where(condition)
                    )
                )
                .mappings()
                .first()
            )
            if not row or row["revoked_at"] or row["expires_at"] <= utcnow():
                raise HTTPException(401, "登录已失效，请重新打开邀请链接或登录")
            if row["role"] == "guest":
                invite = (
                    (
                        await c.execute(
                            select(self.invites).where(self.invites.c.id == row["invite_id"])
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    not invite
                    or invite["bound_user_id"] != row["user_id"]
                    or invite["bound_key"] != key_fingerprint(row["public_key"])
                ):
                    raise HTTPException(403, "设备绑定已重置")
                self.check_invite(invite)
        return row

    async def authenticate(self, request):
        row = await self.session(token=request.cookies.get(COOKIE))
        try:
            timestamp = request.headers["x-device-time"]
            nonce = request.headers["x-device-nonce"]
            signature = request.headers["x-device-proof"]
            if abs(time.time() - int(timestamp)) > 60 or not 16 <= len(nonce) <= 64:
                raise ValueError("Expired request")
            chunks = []
            length = 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > self.db.settings.upload_max_bytes + 1024 * 1024:
                    raise HTTPException(413, "请求体过大")
                chunks.append(chunk)
            body = b"".join(chunks)
            request._body = body  # Starlette's cached request replays the verified body downstream.
            target = request.url.path + ("?" + request.url.query if request.url.query else "")
            verify(
                row["public_key"],
                signature,
                f"{request.method}\n{target}\n{timestamp}\n{nonce}\n{digest(body)}",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(401, "缺少有效的绑定设备签名") from exc
        async with self.db.engine.begin() as c:
            await self.cleanup(c)
            nonce_stmt = (
                insert(self.nonces)
                .values(
                    session_id=row["id"], nonce=nonce, expires_at=utcnow() + timedelta(minutes=2)
                )
                .on_conflict_do_nothing()
                .returning(self.nonces.c.nonce)
            )
            if not (await c.execute(nonce_stmt)).first():
                raise HTTPException(401, "请求签名已使用，请重试")
        return Principal(row["user_id"], row["id"], row["role"], row["name"])

    async def assert_active(self, principal):
        await self.session(session_id=principal.session_id)

    async def create_invite(self, name, valid_from, expires_at):
        if (
            expires_at <= valid_from
            or expires_at <= utcnow()
            or expires_at > utcnow() + timedelta(days=366)
        ):
            raise HTTPException(422, "邀请有效期不合法，最长支持一年")
        token = secrets.token_urlsafe(32)
        id = uuid4()
        async with self.db.engine.begin() as c:
            await c.execute(
                self.invites.insert().values(
                    id=id,
                    name=name,
                    token_hash=digest(token),
                    valid_from=valid_from,
                    expires_at=expires_at,
                    created_at=utcnow(),
                )
            )
        return {
            "id": str(id),
            "token": token,
            "url": f"{self.db.settings.web_origin}/access#invite={token}",
        }
