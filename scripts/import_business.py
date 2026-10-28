"""Import the provided synthetic dataset once; provision a SELECT-only runtime role.

Usage: uv run --project apps/api python scripts/import_business.py /path/to/data.zip
No reset/overwrite operation is provided.
"""

import asyncio
import csv
import hashlib
import io
import json
import os
import secrets
import sys
import zipfile
from pathlib import Path

import asyncpg
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "business_v1"
ROLE = "xiaoma_business_reader"
TABLES = (
    "regions",
    "customers",
    "categories",
    "suppliers",
    "products",
    "orders",
    "order_items",
    "refunds",
    "refund_items",
    "demo_context",
)


async def main(path):
    if path.is_dir():
        ddl = (path / "schema.sql").read_text()
        csv_data = {name: (path / f"csv/{name}.csv").read_bytes() for name in TABLES}
        expected = json.loads((path / "catalog/table_counts.json").read_text())
    else:
        with zipfile.ZipFile(path) as archive:
            ddl = archive.read("data/demo/schema.sql").decode()
            csv_data = {name: archive.read(f"data/demo/csv/{name}.csv") for name in TABLES}
            expected = json.loads(archive.read("data/demo/catalog/table_counts.json"))
    digest = hashlib.sha256(ddl.encode() + b"".join(csv_data.values())).hexdigest()
    env = dotenv_values(ROOT / ".env")
    admin = make_url(env["DATABASE_URL"])
    conn = await asyncpg.connect(
        admin.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(6102801)")
            exists = await conn.fetchval("SELECT to_regnamespace($1)", SCHEMA)
            if exists:
                stamp = await conn.fetchval(
                    "SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname=$1",
                    SCHEMA,
                )
                if stamp != f"xiaoma-dataset-sha256:{digest}":
                    raise RuntimeError("目标 Schema 已存在且不是同一数据包，拒绝覆盖")
            else:
                await conn.execute(f'CREATE SCHEMA "{SCHEMA}"')
                await conn.execute(f'SET LOCAL search_path="{SCHEMA}",pg_catalog')
                await conn.execute("SET LOCAL TIME ZONE 'Asia/Shanghai'")
                await conn.execute(ddl)
                for name, data in csv_data.items():
                    columns = next(csv.reader(io.StringIO(data.decode())))
                    await conn.copy_to_table(
                        name,
                        schema_name=SCHEMA,
                        columns=columns,
                        source=io.BytesIO(data),
                        format="csv",
                        header=True,
                        null="\\N",
                    )
                await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
                await conn.execute(
                    f"COMMENT ON SCHEMA {SCHEMA} IS 'xiaoma-dataset-sha256:{digest}'"
                )
            counts = {
                name: await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}"."{name}"')
                for name in TABLES
            }
            if counts != expected:
                raise RuntimeError("业务表行数与数据包不一致，已回滚")
            role_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", ROLE
            )
            if role_exists:
                current_url = make_url(env.get("BUSINESS_DATABASE_URL") or "postgresql://invalid")
                if current_url.username != ROLE or not current_url.password:
                    raise RuntimeError("只读账号已存在且没有本项目的连接配置，拒绝修改")
                password = current_url.password
            else:
                password = secrets.token_hex(24)
                await conn.execute(
                    f"CREATE ROLE {ROLE} LOGIN PASSWORD '{password}' "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
                )
            await conn.execute(f"ALTER ROLE {ROLE} SET default_transaction_read_only = on")
            await conn.execute(f"ALTER ROLE {ROLE} SET statement_timeout = '5s'")
            await conn.execute(f"ALTER ROLE {ROLE} SET timezone = 'Asia/Shanghai'")
            await conn.execute(f'ALTER ROLE {ROLE} SET search_path = "{SCHEMA}",pg_catalog')
            await conn.execute(f'GRANT CONNECT ON DATABASE "{admin.database}" TO {ROLE}')
            await conn.execute(f'GRANT USAGE ON SCHEMA "{SCHEMA}" TO {ROLE}')
            await conn.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{SCHEMA}" TO {ROLE}')
            await conn.execute(f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA "{SCHEMA}" FROM PUBLIC')
        url = admin.set(drivername="postgresql+asyncpg", username=ROLE, password=password)
        set_key(ROOT / ".env", "BUSINESS_DATABASE_URL", url.render_as_string(hide_password=False))
        set_key(ROOT / ".env", "BUSINESS_SCHEMA", SCHEMA)
        os.chmod(ROOT / ".env", 0o600)
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "tables": counts,
                    "readonly_role": ROLE,
                    "imported": not bool(exists),
                },
                ensure_ascii=False,
            )
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/business"))
