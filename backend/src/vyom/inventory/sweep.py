"""The scheduled inventory sweep: collection that runs whether or not anyone is looking.

Each tick, a worker takes the connection's lease, then collects every due kind in ``SWEEP``
order and records the evidence and the collector's health. Workers that find the lease held
skip the tick, so many API replicas never collect the same connection at once. The lease is
renewed before each kind; a worker that cannot renew stops, because another worker may have
taken over. The store's out-of-order rules keep even an overlapping late write safe.

A kind whose collector fails is not collected again until its backoff passes; the other kinds
continue. A database failure ends the tick and the loop carries on at the next one.
"""

import asyncio
import logging
import os
import socket
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import psycopg

from vyom import telemetry
from vyom.collectors.kubernetes import TableCollector
from vyom.context import TrustedContext
from vyom.credentials import CredentialUnavailable
from vyom.inventory.config import SweepConfig
from vyom.inventory.database import Database

_log = logging.getLogger("vyom.inventory")
# Failures that mean "the database is unreachable or unusable", as the API routes treat them.
_DATABASE_ERRORS = (psycopg.Error, CredentialUnavailable, OSError, TimeoutError)


class SweepOutcome(StrEnum):
    SWEPT = "swept"  # held the lease and visited every kind (due or not)
    LEASE_HELD = "lease_held"  # another worker holds the lease
    LEASE_LOST = "lease_lost"  # stopped part-way: the lease could not be renewed
    DATABASE_UNAVAILABLE = "database_unavailable"


def default_holder() -> str:
    # The pod name (hostname) helps an operator see who holds a lease; the suffix keeps two
    # processes in one pod apart.
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


class Sweeper:
    def __init__(
        self,
        collectors: Sequence[TableCollector],
        database: Database,
        context: TrustedContext,
        config: SweepConfig,
        *,
        holder: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._collectors = tuple(collectors)
        self._database = database
        self._context = context
        self._config = config
        self.holder = holder or default_holder()
        self._clock = clock  # tests only

    async def sweep_once(self) -> SweepOutcome:
        """One tick. Never raises for collector or database failures."""
        started = time.perf_counter()
        error_type = None
        try:
            outcome = await self._sweep()
        except _DATABASE_ERRORS as error:
            outcome, error_type = SweepOutcome.DATABASE_UNAVAILABLE, type(error).__name__
        telemetry.record_inventory_operation(
            "sweep",
            outcome="ok" if outcome is SweepOutcome.SWEPT else outcome.value,
            duration=time.perf_counter() - started,
            error_type=error_type,
        )
        return outcome

    async def _sweep(self) -> SweepOutcome:
        context, config = self._context, self._config
        interval = timedelta(seconds=config.interval_seconds)
        max_backoff = timedelta(seconds=config.max_backoff_seconds)
        async with self._database.store() as store:
            if not await store.acquire_lease(context, self.holder, config.lease_seconds):
                return SweepOutcome.LEASE_HELD
            due = {
                health.kind: health.next_due_at for health in await store.collection_health(context)
            }
            for collector in self._collectors:
                kind = collector.projection.kind
                if kind in due and due[kind] > self._clock():
                    continue  # backing off, or collected recently by another worker
                if not await store.acquire_lease(context, self.holder, config.lease_seconds):
                    return SweepOutcome.LEASE_LOST
                evidence = await collector.collect(context)
                await store.record_collection(context, evidence, kind=kind)
                await store.record_health(
                    context, evidence, kind=kind, interval=interval, max_backoff=max_backoff
                )
            return SweepOutcome.SWEPT

    async def release(self) -> None:
        """Give the lease up, for a clean shutdown. Best effort: it expires anyway."""
        try:
            async with self._database.store() as store:
                await store.release_lease(self._context, self.holder)
        except _DATABASE_ERRORS:
            pass

    async def run(self) -> None:
        """Sweep every interval until cancelled."""
        while True:
            try:
                await self.sweep_once()
            except Exception as error:  # a bug must not end background collection silently
                _log.error("inventory sweep failed", extra={"error_type": type(error).__name__})
            await asyncio.sleep(self._config.interval_seconds)
