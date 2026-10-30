"""Apply the versioned SQL migrations in ``migrations/`` to a Postgres database.

Files are named ``NNNN_description.sql`` and applied in number order. Each file runs in its
own transaction together with the row that records it, so a failing migration leaves neither
a half-built schema nor a version row behind (Postgres DDL is transactional). An advisory
lock stops two processes from migrating at once. Applied files are checked by SHA-256: an
edited migration is refused instead of silently diverging from the databases it already ran
on. Migrations never run on API startup; R2.3 runs them from a controlled Job.
"""

import asyncio
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from importlib.resources import files

import psycopg

from vyom.credentials import CredentialUnavailable
from vyom.inventory.config import DatabaseConfig
from vyom.mcp_client.registry import load_operator_config

# Any fixed 64-bit number works; it only has to be the same for every Vyom process.
_LOCK_ID = 0x7679_6F6D_0001  # "vyom" + 1
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigrationMismatch(Exception):
    """An applied migration differs from the file shipped with this code."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


def available() -> list[Migration]:
    """The migrations shipped in this package, in version order."""
    found = []
    for entry in files("vyom.inventory").joinpath("migrations").iterdir():
        match = _NAME.match(entry.name)
        if match:
            found.append(Migration(int(match.group(1)), entry.name, entry.read_text()))
    found.sort(key=lambda migration: migration.version)
    versions = [migration.version for migration in found]
    if len(set(versions)) != len(versions):
        raise MigrationMismatch("two migration files share a version number")
    return found


async def migrate(conn: psycopg.AsyncConnection) -> list[int]:
    """Apply pending migrations. Returns the versions applied by this call.

    ``conn`` must be in autocommit mode, so that each migration's ``transaction()`` block is
    a real transaction rather than a savepoint inside one the caller left open.
    """
    if not conn.autocommit:
        raise ValueError("migrate() needs an autocommit connection")
    await conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_ID,))
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version integer PRIMARY KEY, name text NOT NULL, checksum text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        rows = await (
            await conn.execute("SELECT version, checksum FROM schema_migrations")
        ).fetchall()
        applied = dict(rows)
        shipped = available()
        unknown = set(applied) - {migration.version for migration in shipped}
        if unknown:
            # The database is newer than this code: refuse rather than run against it.
            raise MigrationMismatch(f"database has migrations this code lacks: {sorted(unknown)}")
        done = []
        for migration in shipped:
            if migration.version in applied:
                if applied[migration.version] != migration.checksum:
                    raise MigrationMismatch(f"migration {migration.name} was changed after it ran")
                continue
            async with conn.transaction():
                await conn.execute(migration.sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                    (migration.version, migration.name, migration.checksum),
                )
            done.append(migration.version)
        return done
    finally:
        await conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))


def _database_config_from_env() -> DatabaseConfig:
    path = os.environ.get("VYOM_CONFIG")
    if path:
        operator = load_operator_config(path)
        if operator.database is not None:
            return operator.database
    ref = os.environ.get("VYOM_DATABASE_CREDENTIAL_REF")
    if not ref and os.environ.get("VYOM_DATABASE_URL"):
        ref = "env:VYOM_DATABASE_URL"
    if not ref:
        raise CredentialUnavailable("no database credential reference configured")
    return DatabaseConfig(credential_ref=ref)


async def _run_cli() -> int:
    try:
        cfg = _database_config_from_env()
        url = cfg.read_connection_string()
        async with await psycopg.AsyncConnection.connect(
            url,
            autocommit=True,
            connect_timeout=int(cfg.connect_timeout_seconds),
        ) as conn:
            applied = await migrate(conn)
    except (
        psycopg.Error,
        CredentialUnavailable,
        MigrationMismatch,
        OSError,
        ValueError,
    ) as error:
        print(f"migration failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print(f"migrations applied: {applied}")
    return 0


def main() -> int:
    return asyncio.run(_run_cli())


if __name__ == "__main__":
    sys.exit(main())
