import os

# vyom.api.app builds its module-level app on import, and with no mode set that is production,
# which refuses the development identity. Tests run in development mode.
os.environ.setdefault("VYOM_MODE", "development")


# --- Real Postgres for the inventory tests -------------------------------------------------
# scripts/postgres-test.sh starts a disposable server and sets VYOM_TEST_DATABASE_URL. Each
# test gets its own new, empty database, dropped afterwards, so tests cannot see each other.
import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def database_url():
    admin_url = os.environ.get("VYOM_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("VYOM_TEST_DATABASE_URL not set; run scripts/postgres-test.sh")
    import psycopg
    from psycopg.conninfo import make_conninfo

    name = f"vyom_test_{uuid.uuid4().hex[:12]}"

    async def admin(sql: str) -> None:
        async with await psycopg.AsyncConnection.connect(admin_url, autocommit=True) as conn:
            await conn.execute(sql)

    asyncio.run(admin(f'CREATE DATABASE "{name}"'))
    try:
        if admin_url.startswith(("postgresql://", "postgres://")):
            from urllib.parse import urlsplit, urlunsplit

            p = urlsplit(admin_url)
            yield urlunsplit((p.scheme, p.netloc, f"/{name}", p.query, p.fragment))
        else:
            yield make_conninfo(admin_url, dbname=name)
    finally:
        asyncio.run(admin(f'DROP DATABASE "{name}" WITH (FORCE)'))
