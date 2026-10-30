"""R2.1 acceptance against a real Postgres server (see scripts/postgres-test.sh).

Each test runs its async body with ``asyncio.run`` against a fresh database, so state from
one test never leaks into another. "Restart" below means a new connection to the same
database: nothing is held in the store object between calls.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from vyom.context import TrustedContext
from vyom.evidence import ErrorKind, ItemDraft, build_evidence
from vyom.inventory.migrate import migrate
from vyom.inventory.store import ConnectionConflict, InventoryStore, ScopeMismatch

pytestmark = pytest.mark.postgres

A = TrustedContext(workspace_id="ws-a", connection_id="kind", cluster_uid="c-1", namespace="demo")
B = TrustedContext(workspace_id="ws-b", connection_id="kind", cluster_uid="c-1", namespace="demo")
T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def pod(name: str, uid: str | None, status: str = "Running", namespace: str = "demo"):
    return ItemDraft(
        kind="Pod", namespace=namespace, name=name, uid=uid, attributes={"status": status}
    )


def evidence(context, pods, *, when, complete=True, errors=(), path="direct"):
    return build_evidence(
        context=context,
        path=path,
        drafts=pods,
        complete=complete,
        errors=errors,
        collector="kubernetes-pods" if path == "direct" else None,
        collected_at=when,
    )


def run(url, body):
    """Migrate, then run ``body(store, conn)`` on a fresh connection."""

    async def main():
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
            await migrate(conn)
            return await body(InventoryStore(conn), conn)

    return asyncio.run(main())


def names(resources):
    return sorted((r.name, r.native_uid) for r in resources)


def test_complete_scan_persists_and_citation_resolves_after_restart(database_url):
    ev = evidence(A, [pod("web-1", "u1"), pod("web-2", "u2", "CrashLoopBackOff")], when=at(0))

    async def record(store, conn):
        await store.record_collection(A, ev, kind="Pod")

    run(database_url, record)
    cited = ev.items[1].id  # the old name-based item ID, as answers cite it today

    async def resolve(store, conn):
        return await store.resolve_citation(A, ev.id, cited)

    citation = run(database_url, resolve)
    assert citation is not None
    assert (citation.name, citation.native_uid) == ("web-2", "u2")
    assert citation.attributes == {"status": "CrashLoopBackOff"}
    assert citation.run_state == "complete" and citation.collected_at == at(0)
    assert citation.resource_id is not None and citation.resource_removed_at is None


def test_other_workspace_cannot_read_or_resolve(database_url):
    ev = evidence(A, [pod("web-1", "u1")], when=at(0))

    async def body(store, conn):
        await store.record_collection(A, ev, kind="Pod")
        return (
            await store.resolve_citation(B, ev.id, ev.items[0].id),
            await store.resources(B),
            await store.resources(A),
        )

    other_citation, other_resources, own = run(database_url, body)
    assert other_citation is None and other_resources == []
    assert names(own) == [("web-1", "u1")]


def test_database_refuses_cross_workspace_references(database_url):
    ev = evidence(A, [pod("web-1", "u1")], when=at(0))
    ev_b = evidence(B, [pod("web-1", "u9")], when=at(0))

    async def body(store, conn):
        await store.record_collection(A, ev, kind="Pod")
        await store.record_collection(B, ev_b, kind="Pod")
        (resource_a,) = await store.resources(A)
        # An observation in workspace B pointing at A's run and A's resource.
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await conn.execute(
                "INSERT INTO observations (workspace_id, run_id, item_id, resource_id, kind,"
                " name, native_uid) VALUES ('ws-b', %s, 'x', %s, 'Pod', 'web-1', 'u1')",
                (ev.id, resource_a.id),
            )
        (resource_b,) = await store.resources(B)
        # A relationship in B between A's resource and B's resource.
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await conn.execute(
                "INSERT INTO relationships (workspace_id, source_id, target_id, type,"
                " first_seen_run_id, last_verified_run_id, last_verified_at)"
                " VALUES ('ws-b', %s, %s, 'owns', %s, %s, now())",
                (resource_a.id, resource_b.id, ev_b.id, ev_b.id),
            )
        # The store refuses to link a resource of another workspace before the database does.
        with pytest.raises(ScopeMismatch):
            await store.link(
                B, run_id=ev_b.id, source_id=resource_a.id, target_id=resource_b.id, type="owns"
            )

    run(database_url, body)


def test_uid_recreation_is_a_new_resource_without_old_edges(database_url):
    first = evidence(A, [pod("web-1", "u1"), pod("db-0", "d1")], when=at(0))
    second = evidence(A, [pod("web-1", "u2"), pod("db-0", "d1")], when=at(5))

    async def body(store, conn):
        await store.record_collection(A, first, kind="Pod")
        old_web, db = sorted(await store.resources(A), key=lambda r: r.name, reverse=True)
        await store.link(A, run_id=first.id, source_id=old_web.id, target_id=db.id, type="uses")
        await store.record_collection(A, second, kind="Pod")
        everything = await store.resources(A, include_removed=True)
        current = await store.resources(A)
        new_web = next(r for r in current if r.name == "web-1")
        return (
            old_web,
            new_web,
            everything,
            current,
            (
                await store.relationships(A, new_web.id),
                await store.relationships(A, db.id),
            ),
        )

    old_web, new_web, everything, current, (new_edges, db_edges) = run(database_url, body)
    assert new_web.id != old_web.id and new_web.first_seen_at == at(5)
    assert names(current) == [("db-0", "d1"), ("web-1", "u2")]
    removed = next(r for r in everything if r.native_uid == "u1")
    assert removed.removed_at == at(5)
    # The old incarnation's edge was retired with it; the new one inherits nothing.
    assert new_edges == [] and db_edges == []


def test_partial_scan_removes_nothing_and_refreshes_only_what_it_saw(database_url):
    full = evidence(A, [pod("web-1", "u1"), pod("web-2", "u2")], when=at(0))
    partial = evidence(
        A,
        [pod("web-1", "u1", "Pending")],
        when=at(5),
        complete=False,
        errors=[ErrorKind.UNAVAILABLE],
    )
    assert partial.state.value == "partial"

    async def body(store, conn):
        await store.record_collection(A, full, kind="Pod")
        await store.record_collection(A, partial, kind="Pod")
        return {r.name: r for r in await store.resources(A)}

    by_name = run(database_url, body)
    assert set(by_name) == {"web-1", "web-2"}
    assert by_name["web-1"].last_seen_at == at(5)
    assert by_name["web-1"].attributes == {"status": "Pending"}
    assert by_name["web-2"].last_seen_at == at(0)  # not seen: not refreshed, not removed


@pytest.mark.parametrize("kind", [ErrorKind.FORBIDDEN, ErrorKind.UNAVAILABLE])
def test_failed_scan_is_recorded_but_changes_no_resource(database_url, kind):
    full = evidence(A, [pod("web-1", "u1")], when=at(0))
    failed = evidence(A, [], when=at(5), complete=False, errors=[kind])
    assert failed.state.value in ("denied", "missing")

    async def body(store, conn):
        await store.record_collection(A, full, kind="Pod")
        await store.record_collection(A, failed, kind="Pod")
        row = await (
            await conn.execute(
                "SELECT state, error_kinds FROM collection_runs WHERE id = %s", (failed.id,)
            )
        ).fetchone()
        return row, await store.resources(A)

    (state, error_kinds), resources = run(database_url, body)
    assert state == failed.state.value and error_kinds == [kind.value]
    assert [(r.name, r.last_seen_at, r.removed_at) for r in resources] == [("web-1", at(0), None)]


def test_truncated_scan_removes_nothing(database_url):
    full = evidence(A, [pod("web-1", "u1"), pod("web-2", "u2")], when=at(0))
    truncated = build_evidence(
        context=A,
        path="direct",
        collector="kubernetes-pods",
        collected_at=at(5),
        drafts=[pod("web-1", "u1"), pod("web-3", "u3")],
        max_items=1,
    )
    assert truncated.coverage.truncated

    async def body(store, conn):
        await store.record_collection(A, full, kind="Pod")
        await store.record_collection(A, truncated, kind="Pod")
        return await store.resources(A)

    assert names(run(database_url, body)) == [("web-1", "u1"), ("web-2", "u2")]


def test_complete_zero_scan_removes_everything_in_its_namespace_only(database_url):
    demo = evidence(A, [pod("web-1", "u1")], when=at(0))
    other_ns = A.model_copy(update={"namespace": "other"})
    other = evidence(other_ns, [pod("job-1", "j1", namespace="other")], when=at(0))
    empty = evidence(A, [], when=at(5))
    assert empty.state.value == "zero"

    async def body(store, conn):
        await store.record_collection(A, demo, kind="Pod")
        await store.record_collection(other_ns, other, kind="Pod")
        await store.record_collection(A, empty, kind="Pod")
        return await store.resources(A), await store.resources(other_ns)

    demo_now, other_now = run(database_url, body)
    assert demo_now == []
    assert names(other_now) == [("job-1", "j1")]


def test_scan_without_uids_records_unresolved_observations_and_removes_nothing(database_url):
    full = evidence(A, [pod("web-1", "u1")], when=at(0))
    mcp = evidence(A, [pod("web-2", None)], when=at(5), path="mcp")

    async def body(store, conn):
        await store.record_collection(A, full, kind="Pod")
        await store.record_collection(A, mcp, kind="Pod")
        return await store.resolve_citation(A, mcp.id, mcp.items[0].id), await store.resources(A)

    citation, resources = run(database_url, body)
    assert citation is not None and citation.resource_id is None and citation.native_uid is None
    assert names(resources) == [("web-1", "u1")]  # a name without a UID proves nothing


def test_older_run_arriving_late_cannot_roll_state_back(database_url):
    older = evidence(A, [pod("web-1", "u1", "Pending")], when=at(0))
    newer = evidence(A, [pod("web-1", "u1", "Running"), pod("web-2", "u2")], when=at(10))
    late_older_complete = evidence(A, [pod("web-1", "u1", "Pending")], when=at(5))

    async def body(store, conn):
        await store.record_collection(A, older, kind="Pod")
        await store.record_collection(A, newer, kind="Pod")
        await store.record_collection(A, late_older_complete, kind="Pod")
        return {r.name: r for r in await store.resources(A)}

    by_name = run(database_url, body)
    assert set(by_name) == {"web-1", "web-2"}  # web-2 was seen later: not removed
    assert by_name["web-1"].attributes == {"status": "Running"}
    assert by_name["web-1"].last_seen_at == at(10)


def test_removed_resource_is_not_revived_by_an_older_run(database_url):
    seen = evidence(A, [pod("web-1", "u1")], when=at(0))
    gone = evidence(A, [], when=at(10))
    late = evidence(A, [pod("web-1", "u1")], when=at(5), complete=False, errors=[ErrorKind.TIMEOUT])

    async def body(store, conn):
        for ev in (seen, gone, late):
            await store.record_collection(A, ev, kind="Pod")
        return await store.resources(A, include_removed=True)

    (web,) = run(database_url, body)
    assert web.removed_at == at(10)


def test_failed_recording_rolls_back_completely(database_url):
    ev = evidence(A, [pod("web-1", "u1")], when=at(0))
    again = ev.model_copy(
        update={"items": (*ev.items, *evidence(A, [pod("web-9", "u9")], when=at(0)).items)}
    )

    async def body(store, conn):
        await store.record_collection(A, ev, kind="Pod")
        # Same evidence ID twice: the run insert fails after the connection was ensured.
        with pytest.raises(psycopg.errors.UniqueViolation):
            await store.record_collection(A, again, kind="Pod")
        count = await (await conn.execute("SELECT count(*) FROM observations")).fetchone()
        return count[0], await store.resources(A)

    observations, resources = run(database_url, body)
    assert observations == 1 and names(resources) == [("web-1", "u1")]


def test_scope_mismatch_and_cluster_conflict_are_refused(database_url):
    ev = evidence(A, [pod("web-1", "u1")], when=at(0))
    moved = A.model_copy(update={"cluster_uid": "c-2"})

    async def body(store, conn):
        with pytest.raises(ScopeMismatch):
            await store.record_collection(B, ev, kind="Pod")
        with pytest.raises(ValueError):
            await store.record_collection(A, ev, kind="Service")
        await store.record_collection(A, ev, kind="Pod")
        with pytest.raises(ConnectionConflict):
            await store.record_collection(
                moved, evidence(moved, [pod("web-1", "u1")], when=at(5)), kind="Pod"
            )
        return await store.resources(A)

    assert names(run(database_url, body)) == [("web-1", "u1")]


def test_prune_runs_retains_referenced_and_recent_runs_within_workspace_only(database_url):
    runs = [evidence(A, [pod("web-1", "u1")], when=at(i)) for i in range(6)]
    other_ev = evidence(B, [pod("web-b", "ub")], when=at(0))

    async def body(store, conn):
        await store.record_collection(B, other_ev, kind="Pod")
        for ev in runs:
            await store.record_collection(A, ev, kind="Pod")
        deleted = await store.prune_runs(A, kind="Pod", max_keep=2)
        rows_a = await (
            await conn.execute(
                "SELECT id FROM collection_runs WHERE workspace_id = 'ws-a' ORDER BY collected_at"
            )
        ).fetchall()
        rows_b = await (
            await conn.execute("SELECT id FROM collection_runs WHERE workspace_id = 'ws-b'")
        ).fetchall()
        return deleted, [r[0] for r in rows_a], [r[0] for r in rows_b]

    deleted, kept_a, kept_b = run(database_url, body)
    # runs[0] is first_seen_run_id, runs[5] is last_seen_run_id; among the 4 unreferenced
    # runs (1, 2, 3, 4), max_keep=2 keeps runs[3] and runs[4] and prunes runs[1] and runs[2].
    assert deleted == 2
    assert kept_a == [runs[0].id, runs[3].id, runs[4].id, runs[5].id]
    assert kept_b == [other_ev.id]
