"""Read-only, allowlisted business catalog and paginated data browsing."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .errors import IngestionError
from .settings import Settings

LABELS = json.loads(Path(__file__).with_name("business_labels.json").read_text())


class BusinessDatabase:
    def __init__(self, settings: Settings):
        self.schema = settings.business_schema
        url = settings.business_database_url.get_secret_value()
        self.engine = create_async_engine(url, pool_pre_ping=True) if url else None

    @asynccontextmanager
    async def connection(self):
        if self.engine is None:
            raise IngestionError("business_unavailable", "业务数据库尚未配置")
        async with self.engine.connect() as conn, conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text("SET LOCAL statement_timeout = '5s'"))
            await conn.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
            role = (
                (
                    await conn.execute(
                        text("""
                SELECT rolsuper, rolcreatedb, rolcreaterole,
                  current_setting('default_transaction_read_only') AS readonly
                FROM pg_roles WHERE rolname = current_user
            """)
                    )
                )
                .mappings()
                .one()
            )
            if (
                role["rolsuper"]
                or role["rolcreatedb"]
                or role["rolcreaterole"]
                or role["readonly"] != "on"
            ):
                raise IngestionError("business_unsafe_role", "业务数据库必须配置独立只读账号")
            writable = (
                await conn.execute(
                    text("""
                SELECT EXISTS (
                  SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                  WHERE n.nspname=:schema AND c.relkind='r' AND
                    (has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
                     OR c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user))
                )
            """),
                    {"schema": self.schema},
                )
            ).scalar()
            if writable:
                raise IngestionError("business_unsafe_role", "业务只读账号包含写权限，请检查授权")
            yield conn

    async def columns(self, conn, name):
        rows = (
            (
                await conn.execute(
                    text("""
            SELECT a.attname AS name, format_type(a.atttypid,a.atttypmod) AS type,
              coalesce(col_description(c.oid,a.attnum),'') AS description,
              a.attnotnull AS required,
              (SELECT string_agg(pg_get_constraintdef(k.oid), '; ')
               FROM pg_constraint k WHERE k.conrelid=c.oid AND a.attnum=ANY(k.conkey))
                AS constraints
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
              JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=:schema AND c.relname=:name AND a.attnum>0
              AND NOT a.attisdropped AND c.relkind='r'
            ORDER BY a.attnum
        """),
                    {"schema": self.schema, "name": name},
                )
            )
            .mappings()
            .all()
        )
        return [
            dict(
                row,
                label=LABELS[name]["labels"].get(row["name"], row["name"]),
                constraints=("NOT NULL; " if row["required"] else "") + (row["constraints"] or ""),
                type="timestamptz" if row["type"] == "timestamp with time zone" else row["type"],
            )
            for row in rows
        ]

    async def catalog(self):
        async with self.connection() as conn:
            items = []
            for name, presentation in LABELS.items():
                columns = await self.columns(conn, name)
                if not columns:
                    continue
                description = (
                    await conn.execute(
                        text("""
                    SELECT obj_description(c.oid) FROM pg_class c JOIN pg_namespace n
                    ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relname=:name
                """),
                        {"schema": self.schema, "name": name},
                    )
                ).scalar()
                count = (
                    await conn.execute(text(f'SELECT count(*) FROM "{self.schema}"."{name}"'))
                ).scalar_one()
                primary = next(c["name"] for c in columns if "PRIMARY KEY" in c["constraints"])
                items.append(
                    {
                        "name": name,
                        "title": presentation["title"],
                        "description": description or "",
                        "primaryKey": primary,
                        "rowCount": count,
                        "columns": columns,
                        "previewColumns": presentation["previewColumns"],
                    }
                )
            return {"items": items, "readonly": True, "schema": self.schema}

    async def rows(self, name: str, query: str, limit: int, offset: int):
        if name not in LABELS:
            raise IngestionError("not_found", "业务表不存在")
        async with self.connection() as conn:
            columns = await self.columns(conn, name)
            if not columns:
                raise IngestionError("not_found", "业务表尚未导入")
            primary = next(c["name"] for c in columns if "PRIMARY KEY" in c["constraints"])
            condition = ""
            params = {"limit": limit, "offset": offset}
            if query.strip():
                condition = " WHERE " + " OR ".join(
                    f'CAST("{c["name"]}" AS text) ILIKE :q ESCAPE chr(92)' for c in columns
                )
                escaped = (
                    query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                params["q"] = f"%{escaped}%"
            table = f'"{self.schema}"."{name}"'
            total = (
                await conn.execute(text(f"SELECT count(*) FROM {table}{condition}"), params)
            ).scalar_one()
            rows = (
                (
                    await conn.execute(
                        text(
                            f'SELECT * FROM {table}{condition} ORDER BY "{primary}" '
                            "LIMIT :limit OFFSET :offset"
                        ),
                        params,
                    )
                )
                .mappings()
                .all()
            )
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    async def close(self):
        if self.engine:
            await self.engine.dispose()
