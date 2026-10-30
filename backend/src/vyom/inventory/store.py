"""Workspace-scoped persistence of collections, resources, observations and relationships.

Every method takes the server-resolved ``TrustedContext`` and scopes its SQL to that
workspace and connection; nothing is looked up by ID alone. The schema's composite foreign
keys refuse cross-workspace references independently of these queries.

Reconciliation rules (docs/CONTINUOUS_OPERATIONS.md, "Observation and detection"):

- Identity is the native UID. A recreated object with the same name is a new resource and
  inherits none of the old one's relationships.
- Only a complete, untruncated, error-free scan whose items all carry UIDs may mark resources
  absent, and only within the scan's own kind and namespace.
- A failed scan is recorded as a run but changes no resource: it neither refreshes
  ``last_seen`` nor removes anything.
- Runs can arrive out of order. An older run never overwrites newer state, never removes a
  resource seen later and never revives a resource removed later.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from vyom.context import TrustedContext
from vyom.evidence import Evidence, State

# Bumped when the stored projection of evidence changes meaning.
CONTRACT_VERSION = 1
# Retain up to 500 historical collection runs per (workspace, connection, scope_kind,
# scope_namespace) that are no longer referenced by any resource or relationship.
DEFAULT_MAX_UNREFERENCED_RUNS = 500


class ScopeMismatch(Exception):
    """The evidence was collected under a different authority than the request's context."""


class ConnectionConflict(Exception):
    """The connection already exists with a different cluster identity."""


@dataclass(frozen=True)
class Citation:
    """One cited item as it was observed, with the current state of its resource."""

    run_id: str
    item_id: str
    collected_at: datetime
    run_state: str
    kind: str
    namespace: str | None
    name: str
    native_uid: str | None
    observed_at: datetime | None
    attributes: dict[str, Any]
    resource_id: uuid.UUID | None  # None: the source gave no UID, so identity is unresolved
    resource_removed_at: datetime | None


@dataclass(frozen=True)
class Resource:
    id: uuid.UUID
    kind: str
    namespace: str | None
    name: str
    native_uid: str
    attributes: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    last_seen_run_id: str
    removed_at: datetime | None


@dataclass(frozen=True)
class Relationship:
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str
    last_verified_at: datetime


class InventoryStore:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def record_collection(
        self, context: TrustedContext, evidence: Evidence, *, kind: str
    ) -> None:
        """Persist one collection of ``kind`` in the context's namespace, atomically."""
        source = evidence.source
        if (source.workspace_id, source.connection_id, source.cluster_uid, source.namespace) != (
            context.workspace_id,
            context.connection_id,
            context.cluster_uid,
            context.namespace,
        ):
            raise ScopeMismatch("evidence scope differs from the request context")
        if any(item.kind != kind for item in evidence.items):
            raise ValueError(f"every item of a {kind} collection must be a {kind}")

        ws, at, run = context.workspace_id, evidence.collected_at, evidence.id
        async with self._conn.transaction(), self._conn.cursor(row_factory=dict_row) as cur:
            await self._ensure_connection(cur, context)
            await cur.execute(
                "INSERT INTO collection_runs (workspace_id, id, connection_id, path, collector,"
                " mcp, scope_kind, scope_namespace, collected_at, state, coverage_complete,"
                " returned, truncated, error_kinds, contract_version)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    ws,
                    run,
                    context.connection_id,
                    source.path,
                    source.collector,
                    Jsonb(source.mcp.model_dump()) if source.mcp else None,
                    kind,
                    context.namespace,
                    at,
                    evidence.state.value,
                    evidence.coverage.complete,
                    evidence.coverage.returned,
                    evidence.coverage.truncated,
                    [error.kind.value for error in evidence.errors],
                    CONTRACT_VERSION,
                ),
            )
            for item in evidence.items:
                resource_id = None
                if item.uid:
                    resource_id = await self._upsert_resource(cur, context, run, at, item)
                await cur.execute(
                    "INSERT INTO observations (workspace_id, run_id, item_id, resource_id, kind,"
                    " namespace, name, native_uid, observed_at, attributes)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    # Pagination can repeat an item; the first observation stands.
                    " ON CONFLICT DO NOTHING",
                    (
                        ws,
                        run,
                        item.id,
                        resource_id,
                        item.kind,
                        item.namespace,
                        item.name,
                        item.uid,
                        item.observed_at,
                        Jsonb(item.attributes),
                    ),
                )
            if self._proves_absence(evidence):
                await self._mark_absent(cur, context, run, at, kind)
            await self._prune_runs(cur, context, kind, max_keep=DEFAULT_MAX_UNREFERENCED_RUNS)

    @staticmethod
    def _proves_absence(evidence: Evidence) -> bool:
        # Without UIDs a missing name cannot be told apart from a recreated object.
        return (
            evidence.state in (State.COMPLETE, State.ZERO)
            and evidence.coverage.complete
            and not evidence.coverage.truncated
            and not evidence.errors
            and all(item.uid for item in evidence.items)
        )

    async def _ensure_connection(self, cur: psycopg.AsyncCursor, context: TrustedContext) -> None:
        await cur.execute(
            "INSERT INTO workspaces (id) VALUES (%s) ON CONFLICT DO NOTHING",
            (context.workspace_id,),
        )
        await cur.execute(
            "INSERT INTO connections (workspace_id, id, provider, cluster_uid)"
            " VALUES (%s, %s, 'kubernetes', %s) ON CONFLICT DO NOTHING",
            (context.workspace_id, context.connection_id, context.cluster_uid),
        )
        await cur.execute(
            "SELECT cluster_uid FROM connections WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, context.connection_id),
        )
        row = await cur.fetchone()
        if row is None or row["cluster_uid"] != context.cluster_uid:
            raise ConnectionConflict("connection is bound to a different cluster")

    async def _upsert_resource(self, cur, context, run, at, item) -> uuid.UUID:
        # The update applies only when this run is at least as new as the stored state and
        # not older than a recorded removal, so late runs cannot roll state back.
        await cur.execute(
            "INSERT INTO resources AS r (workspace_id, connection_id, kind, namespace, name,"
            " native_uid, legacy_ref, attributes, first_seen_at, first_seen_run_id,"
            " last_seen_at, last_seen_run_id)"
            " VALUES (%(ws)s, %(conn)s, %(kind)s, %(ns)s, %(name)s, %(uid)s, %(ref)s,"
            " %(attrs)s, %(at)s, %(run)s, %(at)s, %(run)s)"
            " ON CONFLICT (workspace_id, connection_id, kind, native_uid) DO UPDATE SET"
            " namespace = EXCLUDED.namespace, name = EXCLUDED.name,"
            " legacy_ref = EXCLUDED.legacy_ref, attributes = EXCLUDED.attributes,"
            " last_seen_at = EXCLUDED.last_seen_at, last_seen_run_id = EXCLUDED.last_seen_run_id,"
            " removed_at = NULL, removed_run_id = NULL"
            " WHERE r.last_seen_at <= EXCLUDED.last_seen_at"
            " AND (r.removed_at IS NULL OR r.removed_at < EXCLUDED.last_seen_at)",
            {
                "ws": context.workspace_id,
                "conn": context.connection_id,
                "kind": item.kind,
                "ns": item.namespace,
                "name": item.name,
                "uid": item.uid,
                "ref": item.id,
                "attrs": Jsonb(item.attributes),
                "at": at,
                "run": run,
            },
        )
        await cur.execute(
            "SELECT id FROM resources WHERE workspace_id = %s AND connection_id = %s"
            " AND kind = %s AND native_uid = %s",
            (context.workspace_id, context.connection_id, item.kind, item.uid),
        )
        return (await cur.fetchone())["id"]

    async def _mark_absent(self, cur, context, run, at, kind) -> None:
        # last_seen_at < at excludes everything this run saw (now last_seen_at = at) and
        # everything a newer run saw; namespace keeps a scoped scan inside its scope.
        await cur.execute(
            "UPDATE resources SET removed_at = %(at)s, removed_run_id = %(run)s"
            " WHERE workspace_id = %(ws)s AND connection_id = %(conn)s AND kind = %(kind)s"
            " AND namespace = %(ns)s AND removed_at IS NULL AND last_seen_at < %(at)s"
            " RETURNING id",
            {
                "ws": context.workspace_id,
                "conn": context.connection_id,
                "kind": kind,
                "ns": context.namespace,
                "at": at,
                "run": run,
            },
        )
        removed = [row["id"] for row in await cur.fetchall()]
        if removed:
            await cur.execute(
                "UPDATE relationships SET removed_at = %(at)s, removed_run_id = %(run)s"
                " WHERE workspace_id = %(ws)s AND removed_at IS NULL"
                " AND (source_id = ANY(%(ids)s) OR target_id = ANY(%(ids)s))",
                {"ws": context.workspace_id, "at": at, "run": run, "ids": removed},
            )

    async def _prune_runs(self, cur, context: TrustedContext, kind: str, *, max_keep: int) -> int:
        if max_keep < 1:
            raise ValueError("max_keep must be at least 1")
        params = {
            "ws": context.workspace_id,
            "conn": context.connection_id,
            "kind": kind,
            "ns": context.namespace,
            "keep": max_keep,
        }
        await cur.execute(
            """
            SELECT c.id FROM collection_runs c
            WHERE c.workspace_id = %(ws)s
              AND c.connection_id = %(conn)s
              AND c.scope_kind = %(kind)s
              AND c.scope_namespace IS NOT DISTINCT FROM %(ns)s
              AND NOT EXISTS (
                  SELECT 1 FROM resources r
                  WHERE r.workspace_id = c.workspace_id
                    AND (
                        r.first_seen_run_id = c.id
                        OR r.last_seen_run_id = c.id
                        OR r.removed_run_id = c.id
                    )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM relationships e
                  WHERE e.workspace_id = c.workspace_id
                    AND (
                        e.first_seen_run_id = c.id
                        OR e.last_verified_run_id = c.id
                        OR e.removed_run_id = c.id
                    )
              )
            ORDER BY c.collected_at DESC, c.id DESC
            OFFSET %(keep)s
            """,
            params,
        )
        stale_ids = [row["id"] for row in await cur.fetchall()]
        if not stale_ids:
            return 0
        await cur.execute(
            "DELETE FROM observations WHERE workspace_id = %s AND run_id = ANY(%s)",
            (context.workspace_id, stale_ids),
        )
        await cur.execute(
            "DELETE FROM collection_runs WHERE workspace_id = %s AND id = ANY(%s)",
            (context.workspace_id, stale_ids),
        )
        return len(stale_ids)

    async def prune_runs(
        self,
        context: TrustedContext,
        *,
        kind: str = "Pod",
        max_keep: int = DEFAULT_MAX_UNREFERENCED_RUNS,
    ) -> int:
        """Prune unreferenced collection runs and observations beyond ``max_keep``."""
        async with self._conn.transaction(), self._conn.cursor(row_factory=dict_row) as cur:
            return await self._prune_runs(cur, context, kind, max_keep=max_keep)

    async def resolve_citation(
        self, context: TrustedContext, evidence_id: str, item_id: str
    ) -> Citation | None:
        """The cited observation, or None if it does not exist within this scope.

        Absent and out-of-scope citations are indistinguishable, so a caller cannot probe
        another workspace for existence. Old name-based item IDs resolve unchanged: they are
        the observation's ``item_id``.
        """
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT o.run_id, o.item_id, c.collected_at, c.state AS run_state, o.kind,"
                " o.namespace, o.name, o.native_uid, o.observed_at, o.attributes,"
                " o.resource_id, r.removed_at AS resource_removed_at"
                " FROM observations o"
                " JOIN collection_runs c ON c.workspace_id = o.workspace_id AND c.id = o.run_id"
                " LEFT JOIN resources r"
                "   ON r.workspace_id = o.workspace_id AND r.id = o.resource_id"
                " WHERE o.workspace_id = %s AND c.connection_id = %s"
                " AND o.run_id = %s AND o.item_id = %s",
                (context.workspace_id, context.connection_id, evidence_id, item_id),
            )
            row = await cur.fetchone()
        return Citation(**row) if row else None

    async def resources(
        self, context: TrustedContext, *, kind: str | None = None, include_removed: bool = False
    ) -> list[Resource]:
        """Resources of the context's connection and namespace, latest state first by name."""
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, kind, namespace, name, native_uid, attributes, first_seen_at,"
                " last_seen_at, last_seen_run_id, removed_at FROM resources"
                " WHERE workspace_id = %s AND connection_id = %s AND namespace = %s"
                " AND (%s::text IS NULL OR kind = %s)"
                " AND (%s OR removed_at IS NULL)"
                " ORDER BY kind, name, first_seen_at",
                (
                    context.workspace_id,
                    context.connection_id,
                    context.namespace,
                    kind,
                    kind,
                    include_removed,
                ),
            )
            return [Resource(**row) for row in await cur.fetchall()]

    async def link(
        self,
        context: TrustedContext,
        *,
        run_id: str,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        type: str,
    ) -> None:
        """Record or re-verify an edge seen by ``run_id``. Both ends must be in scope."""
        async with self._conn.transaction(), self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT collected_at FROM collection_runs"
                " WHERE workspace_id = %s AND connection_id = %s AND id = %s",
                (context.workspace_id, context.connection_id, run_id),
            )
            run = await cur.fetchone()
            await cur.execute(
                "SELECT count(*) AS n FROM resources WHERE workspace_id = %s"
                " AND connection_id = %s AND id = ANY(%s)",
                (context.workspace_id, context.connection_id, [source_id, target_id]),
            )
            if run is None or (await cur.fetchone())["n"] != 2:
                raise ScopeMismatch("run or resource is outside the request context")
            await cur.execute(
                "INSERT INTO relationships AS e (workspace_id, source_id, target_id, type,"
                " first_seen_run_id, last_verified_run_id, last_verified_at)"
                " VALUES (%(ws)s, %(src)s, %(dst)s, %(type)s, %(run)s, %(run)s, %(at)s)"
                " ON CONFLICT (workspace_id, source_id, target_id, type) DO UPDATE SET"
                " last_verified_run_id = EXCLUDED.last_verified_run_id,"
                " last_verified_at = EXCLUDED.last_verified_at"
                " WHERE e.last_verified_at <= EXCLUDED.last_verified_at",
                {
                    "ws": context.workspace_id,
                    "src": source_id,
                    "dst": target_id,
                    "type": type,
                    "run": run_id,
                    "at": run["collected_at"],
                },
            )

    async def relationships(
        self, context: TrustedContext, resource_id: uuid.UUID
    ) -> list[Relationship]:
        """Current edges touching a resource of the context's connection."""
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT e.id, e.source_id, e.target_id, e.type, e.last_verified_at"
                " FROM relationships e JOIN resources r"
                "   ON r.workspace_id = e.workspace_id AND r.id = %(id)s"
                " WHERE e.workspace_id = %(ws)s AND r.connection_id = %(conn)s"
                " AND e.removed_at IS NULL AND (e.source_id = %(id)s OR e.target_id = %(id)s)"
                " ORDER BY e.type, e.last_verified_at",
                {"ws": context.workspace_id, "conn": context.connection_id, "id": resource_id},
            )
            return [Relationship(**row) for row in await cur.fetchall()]
