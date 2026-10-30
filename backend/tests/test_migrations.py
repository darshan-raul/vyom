"""Migration runner against a real Postgres server (see scripts/postgres-test.sh)."""

import asyncio

import psycopg
import pytest

from vyom.inventory import migrate as migrations
from vyom.inventory.migrate import Migration, MigrationMismatch, migrate

pytestmark = pytest.mark.postgres

TABLES = {
    "workspaces",
    "connections",
    "collection_runs",
    "resources",
    "observations",
    "relationships",
    "schema_migrations",
}


async def tables(conn) -> set[str]:
    rows = await (
        await conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    ).fetchall()
    return {row[0] for row in rows}


def connect(url):
    return psycopg.AsyncConnection.connect(url, autocommit=True)


def test_applies_once_then_is_a_no_op(database_url):
    async def main():
        async with await connect(database_url) as conn:
            first = await migrate(conn)
            second = await migrate(conn)
            return first, second, await tables(conn)

    first, second, found = asyncio.run(main())
    assert first == [1] and second == [] and found == TABLES


def test_failing_migration_leaves_no_schema_and_no_version(database_url, monkeypatch):
    shipped = migrations.available()
    broken = Migration(2, "0002_broken.sql", "CREATE TABLE half_built (id int); SELECT 1/0;")
    monkeypatch.setattr(migrations, "available", lambda: [*shipped, broken])

    async def main():
        async with await connect(database_url) as conn:
            with pytest.raises(psycopg.errors.DivisionByZero):
                await migrate(conn)
            versions = await (
                await conn.execute("SELECT version FROM schema_migrations")
            ).fetchall()
            return [row[0] for row in versions], await tables(conn)

    versions, found = asyncio.run(main())
    assert versions == [1]  # the good migration stays applied
    assert "half_built" not in found


def test_edited_migration_is_refused(database_url, monkeypatch):
    async def main():
        async with await connect(database_url) as conn:
            await migrate(conn)
            edited = Migration(1, "0001_inventory.sql", "-- edited\n")
            monkeypatch.setattr(migrations, "available", lambda: [edited])
            with pytest.raises(MigrationMismatch):
                await migrate(conn)

    asyncio.run(main())


def test_database_newer_than_code_is_refused(database_url, monkeypatch):
    async def main():
        async with await connect(database_url) as conn:
            await migrate(conn)
            await conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (99, 'x', 'y')"
            )
            with pytest.raises(MigrationMismatch):
                await migrate(conn)

    asyncio.run(main())


def test_requires_autocommit(database_url):
    async def main():
        async with await psycopg.AsyncConnection.connect(database_url) as conn:
            with pytest.raises(ValueError):
                await migrate(conn)

    asyncio.run(main())


def test_shipped_migrations_are_found():
    # Guards packaging: the SQL files must ship inside the wheel/image, not only the repo.
    assert [m.version for m in migrations.available()] == [1]


def test_concurrent_runs_apply_each_migration_once(database_url):
    # Two processes starting together: the advisory lock serialises them.
    async def one():
        async with await connect(database_url) as conn:
            return await migrate(conn)

    async def main():
        return sorted(await asyncio.gather(one(), one()))

    assert asyncio.run(main()) == [[], [1]]


def test_cli_runner_applies_migrations_via_credential_ref(database_url, monkeypatch, capsys):
    monkeypatch.delenv("VYOM_CONFIG", raising=False)
    monkeypatch.setenv("VYOM_DATABASE_URL", database_url)
    assert migrations.main() == 0
    assert "migrations applied: [1]" in capsys.readouterr().out
    assert migrations.main() == 0
    assert "migrations applied: []" in capsys.readouterr().out


def test_cli_runner_fails_cleanly_without_credential(monkeypatch, capsys):
    monkeypatch.delenv("VYOM_CONFIG", raising=False)
    monkeypatch.delenv("VYOM_DATABASE_CREDENTIAL_REF", raising=False)
    monkeypatch.delenv("VYOM_DATABASE_URL", raising=False)
    assert migrations.main() == 1
    err = capsys.readouterr().err
    assert "CredentialUnavailable" in err
