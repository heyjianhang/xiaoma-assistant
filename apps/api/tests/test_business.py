"""Real PostgreSQL checks against the imported synthetic business dataset."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from xiaoma.business import BusinessDatabase
from xiaoma.errors import IngestionError
from xiaoma.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
async def business():
    settings = Settings()
    if not settings.business_database_url.get_secret_value():
        pytest.skip("Import the business dataset to run read-only integration checks")
    database = BusinessDatabase(settings)
    yield database
    await database.close()


async def test_catalog_pagination_search_and_identifier_allowlist(business):
    catalog = await business.catalog()
    counts = {item["name"]: item["rowCount"] for item in catalog["items"]}
    assert counts["orders"] == 5000 and counts["refunds"] == 474
    assert len(counts) == 10
    refunds = next(item for item in catalog["items"] if item["name"] == "refunds")
    accepted = next(c for c in refunds["columns"] if c["name"] == "accepted_at")
    assert "验收" in accepted["description"]
    first = await business.rows("orders", "", 10, 0)
    second = await business.rows("orders", "", 10, 10)
    assert first["total"] == 5000
    assert first["items"][0]["order_id"] == 1 and second["items"][0]["order_id"] == 11
    found = await business.rows("orders", first["items"][0]["order_no"], 10, 0)
    assert found["total"] == 1
    assert (await business.rows("orders", "%' OR 1=1 --", 10, 0))["total"] == 0
    with pytest.raises(IngestionError, match="业务表不存在"):
        await business.rows('orders"; DROP SCHEMA public CASCADE;--', "", 10, 0)


async def test_database_role_rejects_writes_even_if_readonly_setting_is_overridden(business):
    async with business.connection() as conn:
        assert (await conn.execute(text("SHOW transaction_read_only"))).scalar() == "on"
    # This would be a no-op, but PostgreSQL must reject the statement by privilege.
    async with business.engine.connect() as conn, conn.begin():
        await conn.execute(text("SET TRANSACTION READ WRITE"))
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(
                text(f'UPDATE "{business.schema}".orders SET paid_amount=paid_amount WHERE false')
            )


async def test_application_refuses_owner_connection_for_business_queries():
    settings = Settings()
    database = BusinessDatabase(
        settings.model_copy(
            update={
                "business_database_url": settings.database_url,
            }
        )
    )
    try:
        with pytest.raises(IngestionError, match="独立只读账号"):
            await database.catalog()
    finally:
        await database.close()
