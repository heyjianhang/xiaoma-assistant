"""Install the pinned official PGMQ SQL-only distribution without replacing PostgreSQL."""

import asyncio
import hashlib
import json
from pathlib import Path

import asyncpg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


async def main():
    source = ROOT / "third_party/pgmq"
    manifest = json.loads((source / "manifest.json").read_text())
    sql = (source / "pgmq.sql").read_bytes()
    if hashlib.sha256(sql).hexdigest() != manifest["files"]["pgmq.sql"]["sha256"]:
        raise RuntimeError("PGMQ source hash mismatch")
    url = make_url(dotenv_values(ROOT / ".env")["DATABASE_URL"])
    conn = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(6102802)")
            installed = await conn.fetchval("SELECT to_regnamespace('pgmq')")
            if installed:
                if not await conn.fetchval(
                    "SELECT to_regprocedure('pgmq.set_vt(text,bigint,integer)')"
                ):
                    raise RuntimeError("Existing PGMQ installation is incomplete; not overwritten")
                print("PGMQ already installed; unchanged")
                return
            await conn.execute(sql.decode())
            await conn.execute("REVOKE ALL ON SCHEMA pgmq FROM PUBLIC")
            await conn.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA pgmq FROM PUBLIC")
        print("Installed official PGMQ " + manifest["version"] + " (SQL-only)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
