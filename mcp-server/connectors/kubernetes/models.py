"""Internal collection contracts, separate from caller-controlled request fields."""

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class AccessDenied(RuntimeError):
    pass


class CollectionError(RuntimeError):
    """Safe category only; never retain provider response bodies or credentials."""

    CODES = frozenset({"denied", "unavailable", "unsupported", "invalid_response", "limit_exceeded"})

    def __init__(self, code: str):
        self.code = code if code in self.CODES else "unavailable"
        super().__init__(self.code)


@dataclass(frozen=True)
class Resource:
    kind: str
    group: str
    plural: str
    namespaced: bool = True

    def path(self, namespace: str | None) -> str:
        base = "/api/v1" if not self.group else f"/apis/{self.group}"
        if self.namespaced:
            if not isinstance(namespace, str) or not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?", namespace):
                raise AccessDenied("A permitted namespace is required")
            base += f"/namespaces/{namespace}"
        elif namespace is not None:
            raise AccessDenied("Cluster resource cannot have a namespace")
        return f"{base}/{self.plural}"


RESOURCES = (
    Resource("Pod", "", "pods"), Resource("Service", "", "services"),
    Resource("ServiceAccount", "", "serviceaccounts"),
    Resource("PersistentVolumeClaim", "", "persistentvolumeclaims"),
    Resource("Event", "", "events"),
    *(Resource(kind, "apps/v1", plural) for kind, plural in (
        ("Deployment", "deployments"), ("ReplicaSet", "replicasets"),
        ("StatefulSet", "statefulsets"), ("DaemonSet", "daemonsets"))),
    Resource("Job", "batch/v1", "jobs"), Resource("CronJob", "batch/v1", "cronjobs"),
    Resource("Ingress", "networking.k8s.io/v1", "ingresses"),
    Resource("NetworkPolicy", "networking.k8s.io/v1", "networkpolicies"),
    Resource("Role", "rbac.authorization.k8s.io/v1", "roles"),
    Resource("RoleBinding", "rbac.authorization.k8s.io/v1", "rolebindings"),
    Resource("Gateway", "gateway.networking.k8s.io/v1", "gateways"),
    Resource("HTTPRoute", "gateway.networking.k8s.io/v1", "httproutes"),
    Resource("Node", "", "nodes", False),
    Resource("Namespace", "", "namespaces", False),
    Resource("PersistentVolume", "", "persistentvolumes", False),
    Resource("ClusterRole", "rbac.authorization.k8s.io/v1", "clusterroles", False),
    Resource("ClusterRoleBinding", "rbac.authorization.k8s.io/v1", "clusterrolebindings", False),
)
BY_KIND = {resource.kind: resource for resource in RESOURCES}


@dataclass(frozen=True)
class RequestContext:
    """Construct from verified identity/membership, never deserialize a request."""

    tenant_id: UUID
    user_id: UUID
    role: str

    def __post_init__(self):
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.user_id, UUID):
            raise AccessDenied("Verified identity is required")
        if self.role not in {"viewer", "operator", "admin"}:
            raise AccessDenied("Unsupported role")


@dataclass(frozen=True)
class ClusterConnection:
    tenant_id: UUID
    cluster_id: UUID
    flavor: str
    endpoint: str
    # Exact host approved at enrollment. Never accept this from a tool argument.
    approved_host: str
    token_file: str
    ca_file: str

    def __post_init__(self):
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.cluster_id, UUID):
            raise AccessDenied("Invalid cluster identity")
        if self.flavor not in {"eks", "aks", "gke", "self_managed"}:
            raise ValueError("Unsupported Kubernetes flavor")


@dataclass(frozen=True)
class ClusterGrant:
    tenant_id: UUID
    cluster_id: UUID
    user_id: UUID
    namespaces: frozenset[str]
    cluster_kinds: frozenset[str] = frozenset()

    def __post_init__(self):
        if not all(isinstance(value, UUID) for value in (self.tenant_id, self.cluster_id, self.user_id)):
            raise AccessDenied("Invalid grant identity")
        if type(self.namespaces) is not frozenset or type(self.cluster_kinds) is not frozenset:
            raise AccessDenied("Immutable grants are required")
        for namespace in self.namespaces:
            BY_KIND["Pod"].path(namespace)
        if any(kind not in BY_KIND or BY_KIND[kind].namespaced for kind in self.cluster_kinds):
            raise AccessDenied("Invalid cluster-wide grant")

    def authorize(self, context: RequestContext, connection: ClusterConnection):
        if (context.tenant_id != connection.tenant_id or context.tenant_id != self.tenant_id
                or context.user_id != self.user_id or connection.cluster_id != self.cluster_id):
            raise AccessDenied("Cluster access denied")


@dataclass(frozen=True)
class ObjectRecord:
    tenant_id: UUID
    cluster_id: UUID
    uid: str
    kind: str
    namespace: str | None
    name: str
    resource_version: str
    observed_at: datetime
    fields: dict

    @property
    def key(self) -> tuple:
        return self.tenant_id, self.cluster_id, self.kind, self.namespace, self.uid


@dataclass(frozen=True)
class Coverage:
    kind: str
    namespace: str | None
    state: str


@dataclass(frozen=True)
class Snapshot:
    tenant_id: UUID
    cluster_id: UUID
    observed_at: datetime
    objects: tuple[ObjectRecord, ...]
    coverage: tuple[Coverage, ...]

    @property
    def partial(self) -> bool:
        return any(item.state != "complete" for item in self.coverage)
