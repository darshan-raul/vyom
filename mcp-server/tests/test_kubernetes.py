"""Offline connector integration: no cluster credentials or external packages."""

import json
import unittest
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from uuid import UUID

from connectors.kubernetes import ClusterConnection, ClusterGrant, KubernetesOperations, RequestContext
from connectors.kubernetes.analysis import health, posture, topology
from connectors.kubernetes.collector import KubernetesCollector, authorized_records, reconcile
from connectors.kubernetes.models import AccessDenied, CollectionError, Coverage, Resource, Snapshot
from connectors.kubernetes.transport import KubernetesHTTP, NoRedirect


TENANT, USER, CLUSTER = (UUID(int=value) for value in (1, 2, 3))
CONTEXT = RequestContext(TENANT, USER, "viewer")
CONNECTION = ClusterConnection(TENANT, CLUSTER, "eks", "https://cluster.example.com", "cluster.example.com",
    f"/etc/secrets/tenants/{TENANT}/clusters/{CLUSTER}/token",
    f"/etc/secrets/tenants/{TENANT}/clusters/{CLUSTER}/ca.crt")
GRANT = ClusterGrant(TENANT, CLUSTER, USER, frozenset({"team-a"}))


def obj(kind="Pod", name="pod", uid="pod-1", namespace="team-a", **extra):
    result = {"kind": kind, "metadata": {"uid": uid, "name": name, "resourceVersion": "11"}}
    if namespace is not None:
        result["metadata"]["namespace"] = namespace
    result.update(extra)
    return result


def page(*items, token=""):
    return {"items": list(items), "metadata": {"continue": token}}


class FakeTransport:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def get(self, path, params):
        self.calls.append((path, params.copy()))
        key = (path, params.get("continue", ""))
        value = self.replies.get(key, page())
        if isinstance(value, Exception):
            raise value
        return value


class KubernetesTests(unittest.TestCase):
    def collect(self, replies, *, grant=GRANT, kinds=("Pod",), context=CONTEXT, connection=CONNECTION, **limits):
        transport = FakeTransport(replies)
        collector = KubernetesCollector(lambda _: transport, **limits)
        return collector.collect(context, connection, grant, kinds=kinds), transport

    def test_cross_tenant_cluster_and_user_denied_before_transport(self):
        for context, connection, grant in (
            (replace(CONTEXT, tenant_id=UUID(int=9)), CONNECTION, GRANT),
            (CONTEXT, replace(CONNECTION, cluster_id=UUID(int=9)), GRANT),
            (CONTEXT, CONNECTION, replace(GRANT, user_id=UUID(int=9))),
        ):
            calls = []
            with self.assertRaises(AccessDenied):
                KubernetesCollector(lambda conn: calls.append(conn)).collect(context, connection, grant)
            self.assertEqual(calls, [])

    def test_namespace_and_cluster_reads_are_separate(self):
        snapshot, transport = self.collect({}, kinds=("Pod", "Node", "ClusterRole"))
        self.assertEqual([call[0] for call in transport.calls], ["/api/v1/namespaces/team-a/pods"])
        self.assertEqual([item.state for item in snapshot.coverage], ["complete", "not_granted", "not_granted"])
        grant = replace(GRANT, cluster_kinds=frozenset({"Node"}))
        snapshot, transport = self.collect({("/api/v1/nodes", ""): page(obj("Node", namespace=None))}, grant=grant, kinds=("Node",))
        self.assertEqual(transport.calls[0][0], "/api/v1/nodes")
        self.assertEqual(snapshot.objects[0].namespace, None)

    def test_no_namespace_grants_reports_unavailable_coverage(self):
        snapshot, transport = self.collect({}, grant=replace(GRANT, namespaces=frozenset()))
        self.assertEqual(transport.calls, [])
        self.assertTrue(snapshot.partial)
        self.assertEqual(posture(snapshot)["assessment"], "partial")

    def test_invalid_namespaces_cluster_grants_roles_and_unknown_kinds(self):
        for namespace in ("*", "../other", "a/b", "a?x=y", "A"):
            with self.assertRaises(AccessDenied):
                replace(GRANT, namespaces=frozenset({namespace}))
        with self.assertRaises(AccessDenied):
            replace(GRANT, cluster_kinds=frozenset({"Pod"}))
        with self.assertRaises(AccessDenied):
            replace(CONTEXT, role="root")
        with self.assertRaises(CollectionError):
            self.collect({}, kinds=("Secret",))

    def test_pagination_deduplication_and_opaque_resource_version(self):
        first = obj()
        second = obj(name="second", uid="pod-2")
        first["metadata"]["resourceVersion"] = "opaque-string"
        snapshot, transport = self.collect({
            ("/api/v1/namespaces/team-a/pods", ""): page(first, token="cursor"),
            ("/api/v1/namespaces/team-a/pods", "cursor"): page(first, second),
        })
        self.assertEqual(len(snapshot.objects), 2)
        self.assertEqual(snapshot.objects[0].resource_version, "opaque-string")
        self.assertEqual(transport.calls[1][1]["continue"], "cursor")
        self.assertFalse(snapshot.partial)

    def test_repeated_cursor_and_page_object_limits_are_partial(self):
        replies = {("/api/v1/namespaces/team-a/pods", ""): page(obj(), token="cursor"),
                   ("/api/v1/namespaces/team-a/pods", "cursor"): page(obj(), token="cursor")}
        snapshot, _ = self.collect(replies)
        self.assertEqual(snapshot.coverage[0].state, "invalid_response")
        snapshot, _ = self.collect(replies, max_pages=1)
        self.assertEqual(snapshot.coverage[0].state, "limit_exceeded")
        self.assertEqual(len(snapshot.objects), 1)
        snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(obj(), obj(uid="other"))}, max_objects=1)
        self.assertEqual(snapshot.coverage[0].state, "limit_exceeded")

    def test_denial_unavailable_and_missing_api_remain_visible(self):
        for code in ("denied", "unsupported", "unavailable"):
            snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): CollectionError(code)})
            self.assertTrue(snapshot.partial)
            self.assertEqual(posture(snapshot)["assessment"], "partial")
            self.assertEqual(snapshot.coverage[0].state, code)

    def test_wrong_namespace_and_malformed_object_not_accepted(self):
        for raw in (obj(namespace="other"), {"kind": "Secret"}, obj(spec=[]), obj(status={"conditions": None}),
                    obj(spec={"containers": [{"name": "x", "image": {"data": "secret"}}]})):
            snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(raw)})
            self.assertEqual(snapshot.objects, ())
            self.assertEqual(snapshot.coverage[0].state, "invalid_response")

    def test_projection_excludes_secret_bearing_fields(self):
        raw = obj(spec={"containers": [{"name": "worker", "image": "example:v1",
            "env": [{"name": "PASSWORD", "value": "do-not-copy"}], "args": ["do-not-copy"],
            "securityContext": {"privileged": True}}]},
            status={"containerStatuses": [{"name": "worker", "restartCount": 2,
                "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "do-not-copy"}}}]})
        raw["metadata"]["annotations"] = {"last-applied": "do-not-copy"}
        raw["metadata"]["labels"] = {"app": "worker", "secret-label": "do-not-copy"}
        raw["data"] = {"password": "do-not-copy"}
        snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(raw)})
        projected = json.dumps(snapshot.objects[0].fields)
        self.assertNotIn("do-not-copy", projected)
        self.assertIn("example:v1", projected)
        self.assertIn("privileged_container", {item["code"] for item in posture(snapshot)["findings"]})

    def test_topology_uses_uid_namespace_and_granted_nodes(self):
        raw = obj(spec={"nodeName": "node", "volumes": [{"persistentVolumeClaim": {"claimName": "data"}}]})
        raw["metadata"]["ownerReferences"] = [{"uid": "deployment-1", "kind": "Deployment"}]
        replies = {
            ("/api/v1/namespaces/team-a/pods", ""): page(raw),
            ("/apis/apps/v1/namespaces/team-a/deployments", ""): page(obj("Deployment", uid="deployment-1")),
            ("/api/v1/nodes", ""): page(obj("Node", name="node", uid="node-1", namespace=None, spec={"providerID": "aws:///zone/i-test"})),
            ("/api/v1/namespaces/team-a/persistentvolumeclaims", ""): page(obj("PersistentVolumeClaim", name="data", uid="pvc-1")),
        }
        snapshot, _ = self.collect(replies, grant=replace(GRANT, cluster_kinds=frozenset({"Node"})), kinds=("Pod", "Deployment", "Node", "PersistentVolumeClaim"))
        result = topology(snapshot)
        self.assertEqual({item["relation"] for item in result["edges"]}, {"owned_by", "scheduled_on", "uses_claim"})
        self.assertEqual(result["cloud_references"][0]["state"], "unresolved")
        snapshot, _ = self.collect(replies, kinds=("Pod", "Node"))
        self.assertIn("scheduled_on", {item["relation"] for item in topology(snapshot)["unresolved"]})

    def test_service_selector_does_not_join_other_namespace(self):
        a, b = obj(uid="a"), obj(uid="b", namespace="team-b")
        a["metadata"]["labels"] = b["metadata"]["labels"] = {"app": "worker"}
        replies = {("/api/v1/namespaces/team-a/pods", ""): page(a),
                   ("/api/v1/namespaces/team-b/pods", ""): page(b),
                   ("/api/v1/namespaces/team-a/services", ""): page(obj("Service", uid="svc", spec={"selector": {"app": "worker"}}))}
        snapshot, _ = self.collect(replies, grant=replace(GRANT, namespaces=frozenset({"team-a", "team-b"})), kinds=("Pod", "Service"))
        self.assertEqual(topology(snapshot)["edges"], [{"source_uid": "svc", "target_uid": "a", "relation": "selects"}])

    def test_health_distinguishes_unknown_pending_ready_and_completed(self):
        pods = [obj(uid="unknown"), obj(uid="pending", status={"phase": "Pending"}),
                obj(uid="ready", status={"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}),
                obj(uid="done", status={"phase": "Succeeded"})]
        snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(*pods)})
        result = health(snapshot)
        self.assertEqual([item["state"] for item in result["observations"]], ["unknown", "attention", "healthy", "completed"])
        self.assertFalse(result["historical_metrics_available"])

    def test_network_policy_absence_requires_complete_collection(self):
        replies = {("/api/v1/namespaces/team-a/pods", ""): page(obj())}
        snapshot, _ = self.collect(replies, kinds=("Pod", "NetworkPolicy"))
        self.assertIn("namespace_has_no_network_policy", {item["code"] for item in posture(snapshot)["findings"]})
        replies[("/apis/networking.k8s.io/v1/namespaces/team-a/networkpolicies", "")] = CollectionError("denied")
        snapshot, _ = self.collect(replies, kinds=("Pod", "NetworkPolicy"))
        self.assertEqual(posture(snapshot)["findings"], [])

    def test_stale_workload_generation_is_not_healthy(self):
        raw = obj("Deployment", spec={"replicas": 2}, status={"readyReplicas": 2, "observedGeneration": 1})
        raw["metadata"]["generation"] = 2
        snapshot, _ = self.collect({("/apis/apps/v1/namespaces/team-a/deployments", ""): page(raw)}, kinds=("Deployment",))
        self.assertEqual(health(snapshot)["observations"][0]["state"], "unknown")

    def test_rbac_and_service_findings_are_bounded_indicators(self):
        replies = {
            ("/apis/rbac.authorization.k8s.io/v1/namespaces/team-a/roles", ""): page(obj("Role", rules=[{"verbs": ["*"], "resources": ["pods"]}])),
            ("/api/v1/namespaces/team-a/services", ""): page(obj("Service", spec={"type": "LoadBalancer"})),
            ("/apis/rbac.authorization.k8s.io/v1/namespaces/team-a/rolebindings", ""): page(obj("RoleBinding", roleRef={"kind": "ClusterRole", "name": "cluster-admin"})),
        }
        snapshot, _ = self.collect(replies, kinds=("Role", "Service", "RoleBinding"))
        result = posture(snapshot)
        self.assertEqual({item["code"] for item in result["findings"]}, {"wildcard_rbac", "potential_external_service", "cluster_admin_binding"})
        self.assertFalse(result["formal_compliance"])

    def test_reconcile_tombstones_only_complete_scopes(self):
        initial, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(obj())})
        denied, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): CollectionError("denied")})
        current, deleted = reconcile(initial.objects, denied)
        self.assertEqual(current, initial.objects)
        self.assertEqual(deleted, ())
        empty, _ = self.collect({})
        current, deleted = reconcile(initial.objects, empty)
        self.assertEqual(current, ())
        self.assertEqual(deleted, (initial.objects[0].key,))

    def test_retained_history_cannot_bypass_revoked_namespace_or_cluster_grants(self):
        grant = replace(GRANT, cluster_kinds=frozenset({"Node"}))
        snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(obj()),
            ("/api/v1/nodes", ""): page(obj("Node", namespace=None))}, grant=grant, kinds=("Pod", "Node"))
        self.assertEqual(len(authorized_records(CONTEXT, CONNECTION, GRANT, snapshot.objects)), 1)
        revoked = replace(GRANT, namespaces=frozenset())
        self.assertEqual(authorized_records(CONTEXT, CONNECTION, revoked, snapshot.objects), ())
        with self.assertRaises(CollectionError):
            authorized_records(CONTEXT, CONNECTION, GRANT, (replace(snapshot.objects[0], tenant_id=UUID(int=9)),))

    def test_partial_second_page_preserves_observed_and_previous(self):
        initial, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(obj(uid="old"))})
        partial, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(obj(uid="new"), token="next"),
                                  ("/api/v1/namespaces/team-a/pods", "next"): CollectionError("unavailable")})
        current, deleted = reconcile(initial.objects, partial)
        self.assertEqual({record.uid for record in current}, {"old", "new"})
        self.assertEqual(deleted, ())

    def test_reconcile_and_analysis_reject_mixed_tenant_cluster_and_stale_batch(self):
        snapshot, _ = self.collect({("/api/v1/namespaces/team-a/pods", ""): page(obj())})
        foreign = replace(snapshot.objects[0], tenant_id=UUID(int=9))
        for function in (topology, health, posture):
            with self.assertRaises(CollectionError):
                function(replace(snapshot, objects=(foreign,)))
        with self.assertRaises(CollectionError):
            reconcile((foreign,), snapshot)
        with self.assertRaises(CollectionError):
            reconcile(snapshot.objects, replace(snapshot, observed_at=snapshot.observed_at - timedelta(seconds=1)))

    def test_each_cluster_flavor_runs_same_internal_flow(self):
        transport = FakeTransport({("/api/v1/namespaces/team-a/pods", ""): page(obj(status={"phase": "Pending"}))})
        operations = KubernetesOperations(KubernetesCollector(lambda _: transport))
        for flavor in ("eks", "aks", "gke", "self_managed"):
            result = operations.inspect(CONTEXT, replace(CONNECTION, flavor=flavor), GRANT, kinds=("Pod",))
            self.assertEqual(result["health"]["observations"][0]["state"], "attention")
        # Fixture conformance only; not live flavor support evidence.

    def test_transport_rejects_unsafe_endpoint_and_credential_paths(self):
        for endpoint in ("http://cluster.example.com", "https://evil.example.com", "https://user@cluster.example.com", "https://cluster.example.com/path", "https://cluster.example.com?x=1"):
            with self.assertRaises(CollectionError):
                KubernetesHTTP(replace(CONNECTION, endpoint=endpoint))
        with self.assertRaises(CollectionError):
            KubernetesHTTP(replace(CONNECTION, token_file="/tmp/token"))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example.com"))

    def test_transport_get_only_bounded_and_token_read_each_call(self):
        class Response(BytesIO):
            pass
        class Opener:
            def __init__(self): self.requests = []
            def open(self, request, timeout):
                self.requests.append((request, timeout))
                return Response(json.dumps(page()).encode())
        opener = Opener()
        with patch("connectors.kubernetes.transport.ssl.create_default_context"), patch("connectors.kubernetes.transport.build_opener", return_value=opener), patch("pathlib.Path.read_text", side_effect=["token-one", "token-two"]):
            transport = KubernetesHTTP(CONNECTION)
            transport.get("/api/v1/namespaces/team-a/pods", {"limit": 1})
            transport.get("/api/v1/namespaces/team-a/pods", {"limit": 1})
            with self.assertRaises(CollectionError):
                transport.get("/api/v1/namespaces/team-a/secrets", {})
        self.assertEqual([request.get_method() for request, _ in opener.requests], ["GET", "GET"])
        self.assertEqual(opener.requests[1][0].get_header("Authorization"), "Bearer token-two")
        self.assertEqual(opener.requests[0][1], 10)

    def test_transport_sanitizes_http_and_connection_errors(self):
        from unittest.mock import Mock

        cases = [(HTTPError("https://cluster.example.com", 403, "credential-body", {}, BytesIO(b"secret")), "denied"),
                 (HTTPError("https://cluster.example.com", 404, "private-body", {}, BytesIO(b"secret")), "unsupported"),
                 (URLError("private-endpoint-detail"), "unavailable")]
        for error, code in cases:
            opener = Mock()
            opener.open.side_effect = error
            with patch("connectors.kubernetes.transport.ssl.create_default_context"), patch("connectors.kubernetes.transport.build_opener", return_value=opener), patch("pathlib.Path.read_text", return_value="token"):
                transport = KubernetesHTTP(CONNECTION)
                with self.assertRaises(CollectionError) as caught:
                    transport.get("/api/v1/namespaces/team-a/pods", {"limit": 1})
                self.assertEqual(str(caught.exception), code)

    def test_transport_rejects_oversized_and_malformed_responses(self):
        from unittest.mock import Mock

        for payload, code in ((b"x" * (KubernetesHTTP.MAX_BYTES + 1), "limit_exceeded"), (b"not-json", "invalid_response"), (b"[]", "invalid_response")):
            opener = Mock()
            opener.open.return_value = BytesIO(payload)
            with patch("connectors.kubernetes.transport.ssl.create_default_context"), patch("connectors.kubernetes.transport.build_opener", return_value=opener), patch("pathlib.Path.read_text", return_value="token"):
                transport = KubernetesHTTP(CONNECTION)
                with self.assertRaises(CollectionError) as caught:
                    transport.get("/api/v1/namespaces/team-a/pods", {})
                self.assertEqual(caught.exception.code, code)

    def test_event_messages_and_rbac_subjects_are_not_projected(self):
        event = obj("Event", message="do-not-copy", reason="FailedScheduling", involvedObject={"uid": "pod-1"})
        binding = obj("RoleBinding", subjects=[{"name": "do-not-copy"}], roleRef={"kind": "Role", "name": "reader"})
        snapshot, _ = self.collect({("/api/v1/namespaces/team-a/events", ""): page(event),
            ("/apis/rbac.authorization.k8s.io/v1/namespaces/team-a/rolebindings", ""): page(binding)}, kinds=("Event", "RoleBinding"))
        self.assertNotIn("do-not-copy", json.dumps([record.fields for record in snapshot.objects]))
        self.assertEqual(snapshot.objects[0].fields["reason"], "FailedScheduling")


if __name__ == "__main__":
    unittest.main()
