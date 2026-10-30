"""Connection management for the PostgreSQL inventory database."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg

from vyom.inventory.config import DatabaseConfig
from vyom.inventory.store import InventoryStore


class Database:
    """Provides workspace-scoped InventoryStore instances from configured credentials."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    @asynccontextmanager
    async def store(self) -> AsyncIterator[InventoryStore]:
        """Open a connection, yield an InventoryStore, and close the connection afterwards."""
        url = self._config.read_connection_string()
        async with await psycopg.AsyncConnection.connect(
            url,
            autocommit=True,
            connect_timeout=int(self._config.connect_timeout_seconds),
        ) as conn:
            yield InventoryStore(conn)
