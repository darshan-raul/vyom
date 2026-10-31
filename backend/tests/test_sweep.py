"""R3.2 scheduled collection. The sweep, lease and backoff run against a real Postgres server
(see scripts/postgres-test.sh) with scripted collectors; the lifespan wiring runs offline.
The live closed-browser check is part of the R3.6 Kind gate."""

import asyncio
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from vyom.api.app import create_app
from vyom.collectors.kubernetes import DEPLOYMENT, POD, REPLICA_SET, KubernetesApiConfig
from vyom.context import TrustedContext
from vyom.evidence import ErrorKind, ItemDraft, OwnerRef, build_evidence
from vyom.inventory import Database, DatabaseConfig
from vyom.inventory.config import SweepConfig
from vyom.inventory.migrate import migrate
from vyom.inventory.sweep import Sweeper, SweepOutcome
from vyom.mcp_client.registry import OperatorConfig

CONTEXT = TrustedContext(
    workspace_id="ws-a", connection_id="kind", cluster_uid="c-1", namespace="demo"
)
CONFIG = SweepConfig(interval_seconds=60, max_backoff_seconds=300, lease_seconds=60)
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(seconds=60)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def owned(kind, name, uid, owner=None):
    return ItemDraft(
        kind=kind,
        namespace="demo",
        name=name,
        uid=uid,
        owner=OwnerRef(kind=owner[0], name=owner[1], uid=owner[2]) if owner else None,
    )


ITEMS = {
    "Deployment": [owned("Deployment", "web", "d1")],
    "ReplicaSet": [owned("ReplicaSet", "web-a", "r1", ("Deployment", "web", "d1"))],
    "Pod": [owned("Pod", "web-a-1", "p1", ("ReplicaSet", "web-a", "r1"))],
}


class FakeCollector:
    """Stands in for a TableCollector: same projection, scripted evidence."""

    def __init__(self, projection, clock, *, gate: asyncio.Event | None = None) -> None:
        self.projection = projection
        self.clock = clock
        self.calls = 0
        self.failing = False
        self.gate = gate  # when set, collect waits for it (to hold the lease mid-sweep)
        self.entered = asyncio.Event()

    async def collect(self, context):
        self.calls += 1
        self.entered.set()
        if self.gate:
            await self.gate.wait()
        kind = self.projection.kind
        return build_evidence(
            context=context,
            path="direct",
            drafts=[] if self.failing else ITEMS[kind],
            complete=not self.failing,
            errors=[ErrorKind.UNAVAILABLE] if self.failing else [],
            collector=self.projection.collector,
            collected_at=self.clock(),
        )


@pytest.fixture
def database(database_url, monkeypatch):
    monkeypatch.setenv("VYOM_TEST_SWEEP_DATABASE", database_url)

    async def setup():
        async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
            await migrate(conn)

    asyncio.run(setup())
    return Database(DatabaseConfig(credential_ref="env:VYOM_TEST_SWEEP_DATABASE"))


def sweeper(database, clock, *, holder, gate=None):
    collectors = [FakeCollector(p, clock, gate=gate) for p in (DEPLOYMENT, REPLICA_SET, POD)]
    return Sweeper(collectors, database, CONTEXT, CONFIG, holder=holder, clock=clock), {
        c.projection.kind: c for c in collectors
    }


async def stored(database):
    async with database.store() as store:
        resources = await store.resources(CONTEXT, include_removed=True)
        health = {h.kind: h for h in await store.collection_health(CONTEXT)}
        return {(r.kind, r.name): r for r in resources}, health


@pytest.mark.postgres
def test_a_sweep_collects_every_kind_with_no_request(database):
    clock = Clock()
    worker, collectors = sweeper(database, clock, holder="a")

    async def main():
        outcome = await worker.sweep_once()
        resources, health = await stored(database)
        async with database.store() as store:
            pod = resources[("Pod", "web-a-1")]
            edges = await store.relationships(CONTEXT, pod.id)
        return outcome, resources, health, edges

    outcome, resources, health, edges = asyncio.run(main())
    assert outcome is SweepOutcome.SWEPT
    assert set(resources) == {("Deployment", "web"), ("ReplicaSet", "web-a"), ("Pod", "web-a-1")}
    # Owners were stored first, so the pod is linked to its ReplicaSet in the same sweep.
    assert [(e.source_id, e.type) for e in edges] == [
        (resources[("ReplicaSet", "web-a")].id, "owns")
    ]
    assert {
        kind: (h.consecutive_failures, h.last_success_at, h.next_due_at)
        for kind, h in health.items()
    } == {kind: (0, T0, T0 + INTERVAL) for kind in ("Deployment", "ReplicaSet", "Pod")}
    assert all(c.calls == 1 for c in collectors.values())


@pytest.mark.postgres
def test_two_workers_never_sweep_one_connection_at_once(database):
    clock = Clock()

    async def main():
        gate = asyncio.Event()
        first, first_collectors = sweeper(database, clock, holder="a", gate=gate)
        second, second_collectors = sweeper(database, clock, holder="b")
        running = asyncio.create_task(first.sweep_once())
        await first_collectors["Deployment"].entered.wait()  # a holds the lease mid-sweep
        blocked = await second.sweep_once()
        gate.set()
        return blocked, await running, first_collectors, second_collectors

    blocked, finished, first_collectors, second_collectors = asyncio.run(main())
    assert blocked is SweepOutcome.LEASE_HELD and finished is SweepOutcome.SWEPT
    assert all(c.calls == 1 for c in first_collectors.values())
    assert all(c.calls == 0 for c in second_collectors.values())


@pytest.mark.postgres
def test_a_lost_worker_lease_expires_and_another_takes_over(database):
    clock = Clock()
    worker, collectors = sweeper(database, clock, holder="b")

    async def main():
        async with database.store() as store:
            # Worker "a" took a short lease and died without releasing it.
            assert await store.acquire_lease(CONTEXT, "a", 0.5)
        held = await worker.sweep_once()
        await asyncio.sleep(0.7)
        return held, await worker.sweep_once()

    held, after = asyncio.run(main())
    assert held is SweepOutcome.LEASE_HELD and after is SweepOutcome.SWEPT
    assert all(c.calls == 1 for c in collectors.values())


@pytest.mark.postgres
def test_released_lease_lets_the_next_worker_in_at_once(database):
    clock = Clock()
    first, _ = sweeper(database, clock, holder="a")
    second, collectors = sweeper(database, clock, holder="b")

    async def main():
        await first.sweep_once()
        await first.release()
        clock.now += INTERVAL
        return await second.sweep_once()

    assert asyncio.run(main()) is SweepOutcome.SWEPT
    assert all(c.calls == 1 for c in collectors.values())


@pytest.mark.postgres
def test_a_failing_kind_backs_off_without_removing_anything_while_others_continue(database):
    clock = Clock()
    worker, collectors = sweeper(database, clock, holder="a")
    pods = collectors["Pod"]

    async def tick(at):
        clock.now = T0 + at * INTERVAL
        await worker.sweep_once()
        return await stored(database)

    async def main():
        await tick(0)  # baseline: everything collected
        pods.failing = True
        resources, first_failure = await tick(1)
        _, skipped = await tick(2)  # pods backing off; others collected
        calls_while_backing_off = (pods.calls, collectors["Deployment"].calls)
        _, second_failure = await tick(3)
        _, capped = await tick(7)
        pods.failing = False
        _, recovered = await tick(12)
        return (
            resources,
            first_failure,
            skipped,
            calls_while_backing_off,
            second_failure,
            capped,
            recovered,
        )

    resources, first, skipped, calls, second, capped, recovered = asyncio.run(main())
    # A failed scan proves nothing: the pod is neither removed nor refreshed.
    pod = resources[("Pod", "web-a-1")]
    assert pod.removed_at is None and pod.last_seen_at == T0
    h = first["Pod"]
    assert (h.last_state, h.last_error_kinds, h.consecutive_failures) == (
        "missing",
        ["unavailable"],
        1,
    )
    assert (h.last_success_at, h.next_due_at) == (T0, T0 + 3 * INTERVAL)  # 2^1 intervals
    assert skipped["Pod"].last_attempt_at == T0 + INTERVAL  # not attempted at tick 2
    assert skipped["Deployment"].last_attempt_at == T0 + 2 * INTERVAL
    assert calls == (2, 3)
    assert (second["Pod"].consecutive_failures, second["Pod"].next_due_at) == (2, T0 + 7 * INTERVAL)
    # 2^3 intervals would be 480 s; the 300 s cap applies.
    assert capped["Pod"].next_due_at == T0 + 7 * INTERVAL + timedelta(seconds=300)
    r = recovered["Pod"]
    assert (r.consecutive_failures, r.last_success_at, r.next_due_at) == (
        0,
        T0 + 12 * INTERVAL,
        T0 + 13 * INTERVAL,
    )


@pytest.mark.postgres
def test_health_is_scoped_to_the_workspace(database):
    clock = Clock()
    worker, _ = sweeper(database, clock, holder="a")
    other = CONTEXT.model_copy(update={"workspace_id": "ws-b"})

    async def main():
        await worker.sweep_once()
        async with database.store() as store:
            return await store.collection_health(other)

    assert asyncio.run(main()) == []


def test_an_unreachable_database_is_an_outcome_not_an_exception(monkeypatch):
    monkeypatch.delenv("VYOM_TEST_NO_DATABASE", raising=False)
    database = Database(DatabaseConfig(credential_ref="env:VYOM_TEST_NO_DATABASE"))
    worker, collectors = sweeper(database, Clock(), holder="a")

    assert asyncio.run(worker.sweep_once()) is SweepOutcome.DATABASE_UNAVAILABLE
    assert all(c.calls == 0 for c in collectors.values())


class RecordingSweeper:
    def __init__(self) -> None:
        self.started = False
        self.cancelled = False
        self.released = False

    async def run(self) -> None:
        self.started = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def release(self) -> None:
        self.released = True


def test_the_sweep_runs_for_the_life_of_the_app_without_any_request():
    recording = RecordingSweeper()
    app = create_app(sweeper=recording)

    with TestClient(app):
        pass  # no request is made

    assert recording.started and recording.cancelled and recording.released


def test_a_configured_sweep_without_a_database_refuses_to_start(monkeypatch):
    monkeypatch.setenv("VYOM_TEST_COLLECTOR_TOKEN", "token")
    operator = OperatorConfig(
        context=CONTEXT,
        kubernetes=KubernetesApiConfig(
            connection_id="kind",
            url="https://kubernetes.test",
            credential_ref="env:VYOM_TEST_COLLECTOR_TOKEN",
        ),
        inventory=CONFIG,
    )
    with pytest.raises(ValueError, match="sweep needs"):
        create_app(operator)
