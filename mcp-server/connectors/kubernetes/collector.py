"""Authorized, paginated snapshots. Watch ingestion is a later B11.4 gate."""

from datetime import datetime, timezone
from typing import Callable

from .models import BY_KIND, CollectionError, Coverage, Snapshot
from .normalize import normalize
from .transport import KubernetesHTTP


class KubernetesCollector:
    def __init__(self, transport_factory: Callable = KubernetesHTTP, *, page_size=200, max_pages=50, max_objects=10000):
        if not (1 <= page_size <= 500 and 1 <= max_pages <= 100 and 1 <= max_objects <= 50000):
            raise ValueError("Invalid collection limits")
        self.transport_factory = transport_factory
        self.page_size, self.max_pages, self.max_objects = page_size, max_pages, max_objects

    def collect(self, context, connection, grant, *, kinds: tuple[str, ...] | None = None) -> Snapshot:
        grant.authorize(context, connection)
        kinds = kinds if kinds is not None else tuple(BY_KIND)
        if not kinds or any(kind not in BY_KIND for kind in kinds):
            raise CollectionError("denied")
        # Authorize before credentials are read or a transport is constructed.
        transport = self.transport_factory(connection)
        observed_at = datetime.now(timezone.utc)
        objects, coverage = {}, []
        for kind in dict.fromkeys(kinds):
            resource = BY_KIND[kind]
            scopes = sorted(grant.namespaces) if resource.namespaced else [None]
            if not scopes:
                coverage.append(Coverage(kind, None, "not_granted"))
                continue
            if not resource.namespaced and kind not in grant.cluster_kinds:
                coverage.append(Coverage(kind, None, "not_granted"))
                continue
            for namespace in scopes:
                path = resource.path(namespace)
                collected, seen_tokens, token = {}, set(), ""
                try:
                    for _ in range(self.max_pages):
                        params = {"limit": self.page_size}
                        if token:
                            params["continue"] = token
                        data = transport.get(path, params)
                        if (not isinstance(data, dict) or not isinstance(data.get("items"), list)
                                or not isinstance(data.get("metadata", {}), dict)):
                            raise CollectionError("invalid_response")
                        for raw in data["items"]:
                            record = normalize(raw, resource, namespace, connection, observed_at)
                            if record.key not in collected and len(collected) + len(objects) >= self.max_objects:
                                raise CollectionError("limit_exceeded")
                            collected[record.key] = record
                        token = data.get("metadata", {}).get("continue", "")
                        if not isinstance(token, str) or len(token) > 4096:
                            raise CollectionError("invalid_response")
                        if not token:
                            break
                        if token in seen_tokens:
                            raise CollectionError("invalid_response")
                        seen_tokens.add(token)
                    else:
                        raise CollectionError("limit_exceeded")
                    coverage.append(Coverage(kind, namespace, "complete"))
                except CollectionError as exc:
                    coverage.append(Coverage(kind, namespace, exc.code))
                # Preserve observations even on a later-page failure, while the
                # incomplete scope prevents reconciliation tombstones.
                objects.update(collected)
        return Snapshot(connection.tenant_id, connection.cluster_id, observed_at, tuple(objects.values()), tuple(coverage))


def reconcile(previous: tuple, snapshot: Snapshot) -> tuple[tuple, tuple]:
    """Return current records and tombstoned keys; never delete denied scopes.

    Internal storage transition only, never a caller-visible authorization view.
    Apply authorized_records with current grants before returning retained data.
    Persistence, scheduling and history TTL remain B11.
    resourceVersion is opaque; ordering follows serial snapshot collection.
    """
    if any(record.tenant_id != snapshot.tenant_id or record.cluster_id != snapshot.cluster_id
           for record in (*previous, *snapshot.objects)):
        raise CollectionError("denied")
    if any(record.observed_at > snapshot.observed_at for record in previous):
        raise CollectionError("invalid_response")
    complete = {(item.kind, item.namespace) for item in snapshot.coverage if item.state == "complete"}
    new = {record.key: record for record in snapshot.objects}
    deleted = tuple(record.key for record in previous if (record.kind, record.namespace) in complete and record.key not in new)
    current = {record.key: record for record in previous if record.key not in deleted}
    current.update(new)
    return tuple(current.values()), deleted


def authorized_records(context, connection, grant, records: tuple) -> tuple:
    """Filter retained storage observations with the current server-resolved grant.

    A failed collection should not delete history, but history retention must not
    let a revoked namespace/cluster-wide grant keep reading that history.
    """
    grant.authorize(context, connection)
    if any(record.tenant_id != connection.tenant_id or record.cluster_id != connection.cluster_id for record in records):
        raise CollectionError("denied")
    return tuple(record for record in records
                 if (record.namespace in grant.namespaces if BY_KIND[record.kind].namespaced
                     else record.kind in grant.cluster_kinds))
