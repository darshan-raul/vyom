"""R3.1 ownership edges against a real Postgres server (see scripts/postgres-test.sh).

Deployments, ReplicaSets and Pods are recorded the way a sweep records them, owners first;
each owned item names its controller and the store keeps ``owns`` edges in step.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from vyom.context import TrustedContext
from vyom.evidence import ErrorKind, ItemDraft, OwnerRef, build_evidence
from vyom.inventory.migrate import migrate
from vyom.inventory.store import OWNS, InventoryStore

pytestmark = pytest.mark.postgres

A = TrustedContext(workspace_id="ws-a", connection_id="kind", cluster_uid="c-1", namespace="demo")
T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def item(kind: str, name: str, uid: str, owner: tuple[str, str, str] | None = None):
    return ItemDraft(
        kind=kind,
        namespace="demo",
        name=name,
        uid=uid,
        owner=OwnerRef(kind=owner[0], name=owner[1], uid=owner[2]) if owner else None,
    )


DEPLOY = item("Deployment", "web", "d1")
RS1 = item("ReplicaSet", "web-aaa", "r1", ("Deployment", "web", "d1"))
RS2 = item("ReplicaSet", "web-bbb", "r2", ("Deployment", "web", "d1"))


def pod(name: str, uid: str, rs: ItemDraft | None):
    return item("Pod", name, uid, (rs.kind, rs.name, rs.uid) if rs else None)


def scan(kind, items, *, when, complete=True, errors=()):
    return kind, build_evidence(
        context=A,
        path="direct",
        drafts=items,
        complete=complete,
        errors=errors,
        collector=f"kubernetes-{kind.lower()}s",
        collected_at=when,
    )


def run(url, *scans):
    """Record ``scans`` in order on a fresh connection, then return every current edge as
    (owner name, owner uid, owned name, owned uid) and the store, connection and evidence."""

    async def main():
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
            await migrate(conn)
            store = InventoryStore(conn)
            for kind, evidence in scans:
                await store.record_collection(A, evidence, kind=kind)
            return await edges(conn)

    return asyncio.run(main())


async def edges(conn):
    cur = await conn.execute(
        "SELECT s.name, s.native_uid, t.name, t.native_uid FROM relationships e"
        " JOIN resources s ON s.workspace_id = e.workspace_id AND s.id = e.source_id"
        " JOIN resources t ON t.workspace_id = e.workspace_id AND t.id = e.target_id"
        " WHERE e.removed_at IS NULL AND e.type = %s ORDER BY 1, 3",
        (OWNS,),
    )
    return await cur.fetchall()


def test_sweep_records_the_deployment_replicaset_pod_chain(database_url):
    pods = scan("Pod", [pod("web-aaa-1", "p1", RS1), pod("web-aaa-2", "p2", RS1)], when=at(0))
    found = run(
        database_url,
        scan("Deployment", [DEPLOY], when=at(0)),
        scan("ReplicaSet", [RS1], when=at(0)),
        pods,
    )
    assert found == [
        ("web", "d1", "web-aaa", "r1"),
        ("web-aaa", "r1", "web-aaa-1", "p1"),
        ("web-aaa", "r1", "web-aaa-2", "p2"),
    ]

    # The cited pod still shows the controller it reported, from the observation itself.
    async def cite():
        async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
            return await InventoryStore(conn).resolve_citation(A, pods[1].id, pods[1].items[0].id)

    citation = asyncio.run(cite())
    assert citation.owner == OwnerRef(kind="ReplicaSet", name="web-aaa", uid="r1")


def test_rollout_moves_pods_to_the_new_replicaset_and_retires_old_edges(database_url):
    found = run(
        database_url,
        scan("Deployment", [DEPLOY], when=at(0)),
        scan("ReplicaSet", [RS1], when=at(0)),
        scan("Pod", [pod("web-aaa-1", "p1", RS1)], when=at(0)),
        # Rollout: the old ReplicaSet stays (scaled to zero), its pod is replaced.
        scan("Deployment", [DEPLOY], when=at(5)),
        scan("ReplicaSet", [RS1, RS2], when=at(5)),
        scan("Pod", [pod("web-bbb-1", "p9", RS2)], when=at(5)),
    )
    assert found == [
        ("web", "d1", "web-aaa", "r1"),
        ("web", "d1", "web-bbb", "r2"),
        ("web-bbb", "r2", "web-bbb-1", "p9"),
    ]


def test_a_newer_observation_with_another_or_no_controller_supersedes_the_edge(database_url):
    other = item("ReplicaSet", "web-ccc", "r3")
    found = run(
        database_url,
        scan("ReplicaSet", [RS1, other], when=at(0)),
        scan("Pod", [pod("a", "p1", RS1), pod("b", "p2", RS1)], when=at(0)),
        # p1 adopted by another ReplicaSet, p2 orphaned.
        scan("Pod", [pod("a", "p1", other), pod("b", "p2", None)], when=at(5)),
    )
    assert found == [("web-ccc", "r3", "a", "p1")]


def test_an_older_run_arriving_late_changes_no_edge(database_url):
    found = run(
        database_url,
        scan("ReplicaSet", [RS1, RS2], when=at(0)),
        scan("Pod", [pod("a", "p1", RS2)], when=at(10)),
        scan("Pod", [pod("a", "p1", RS1)], when=at(5)),  # late: older than what is stored
    )
    assert found == [("web-bbb", "r2", "a", "p1")]


def test_controller_not_stored_leaves_no_edge_until_it_is(database_url):
    job_pod = item("Pod", "migrate-x", "p5", ("Job", "migrate", "j1"))  # a kind not collected
    found = run(
        database_url,
        # The ReplicaSet scan failed, so the pod's controller is not stored yet.
        scan("ReplicaSet", [], when=at(0), complete=False, errors=[ErrorKind.TIMEOUT]),
        scan("Pod", [pod("a", "p1", RS1), job_pod], when=at(0)),
    )
    assert found == []
    found = run(
        database_url,
        scan("ReplicaSet", [RS1], when=at(5)),
        scan("Pod", [pod("a", "p1", RS1), job_pod], when=at(5)),
    )
    assert found == [("web-aaa", "r1", "a", "p1")]


def test_a_removed_controller_is_not_linked_by_a_stale_reference(database_url):
    found = run(
        database_url,
        scan("ReplicaSet", [RS1], when=at(0)),
        scan("ReplicaSet", [], when=at(5)),  # complete and empty: RS1 is gone
        # The pod still names it while garbage collection catches up.
        scan("Pod", [pod("a", "p1", RS1)], when=at(6)),
    )
    assert found == []


def test_a_failed_later_page_keeps_unseen_edges_and_proves_no_absence(database_url):
    found = run(
        database_url,
        scan("ReplicaSet", [RS1], when=at(0)),
        scan("Pod", [pod("a", "p1", RS1), pod("b", "p2", RS1)], when=at(0)),
        # Page two failed: b was not seen, which says nothing about it.
        scan(
            "Pod",
            [pod("a", "p1", RS1)],
            when=at(5),
            complete=False,
            errors=[ErrorKind.UNAVAILABLE],
        ),
    )
    assert found == [("web-aaa", "r1", "a", "p1"), ("web-aaa", "r1", "b", "p2")]


def test_a_recreated_replicaset_is_a_new_owner_that_inherits_nothing(database_url):
    recreated = item("ReplicaSet", "web-aaa", "r1-new", ("Deployment", "web", "d1"))
    found = run(
        database_url,
        scan("Deployment", [DEPLOY], when=at(0)),
        scan("ReplicaSet", [RS1], when=at(0)),
        scan("Pod", [pod("a", "p1", RS1)], when=at(0)),
        # Same name, new UID; the old pods were deleted with it and a new one created.
        scan("ReplicaSet", [recreated], when=at(5)),
        scan("Pod", [pod("a", "p2", recreated)], when=at(5)),
    )
    assert found == [("web", "d1", "web-aaa", "r1-new"), ("web-aaa", "r1-new", "a", "p2")]
