"""Deterministic topology, health and bounded posture from normalized evidence."""

from .models import CollectionError, Snapshot


def validate_scope(snapshot: Snapshot):
    if any(record.tenant_id != snapshot.tenant_id or record.cluster_id != snapshot.cluster_id
           for record in snapshot.objects):
        raise CollectionError("denied")


def topology(snapshot: Snapshot) -> dict:
    validate_scope(snapshot)
    by_uid = {record.uid: record for record in snapshot.objects}
    by_name = {(record.kind, record.namespace, record.name): record for record in snapshot.objects}
    edges, unresolved = [], []

    def link(source, relation, target):
        if target is None:
            unresolved.append({"source_uid": source.uid, "relation": relation})
        else:
            edges.append({"source_uid": source.uid, "target_uid": target.uid, "relation": relation})

    for record in snapshot.objects:
        for owner in record.fields.get("owners", []):
            target = by_uid.get(owner["uid"])
            if target and (target.namespace != record.namespace or target.kind != owner["kind"]):
                target = None
            link(record, "owned_by", target)
        if record.kind == "Pod":
            node = record.fields.get("node_name")
            if node:
                link(record, "scheduled_on", by_name.get(("Node", None, node)))
            for claim in record.fields.get("claims", []):
                link(record, "uses_claim", by_name.get(("PersistentVolumeClaim", record.namespace, claim)))
        elif record.kind == "PersistentVolumeClaim" and record.fields.get("volume_name"):
            link(record, "bound_to", by_name.get(("PersistentVolume", None, record.fields["volume_name"])))
        elif record.kind == "Service":
            selector = record.fields.get("selector", {})
            if selector:
                for pod in snapshot.objects:
                    if (pod.kind == "Pod" and pod.namespace == record.namespace
                            and all(pod.fields.get("labels", {}).get(key) == value for key, value in selector.items())):
                        link(record, "selects", pod)
    # provider IDs are unresolved evidence, never permission to join an account.
    cloud_refs = [{"node_uid": record.uid, "provider_id": record.fields["provider_id"], "state": "unresolved"}
                  for record in snapshot.objects if record.kind == "Node" and record.fields.get("provider_id")]
    return {"edges": edges, "unresolved": unresolved, "cloud_references": cloud_refs}


def health(snapshot: Snapshot) -> dict:
    validate_scope(snapshot)
    observations = []
    for record in snapshot.objects:
        state = "unknown"
        fields = record.fields
        if record.kind == "Pod":
            conditions = {item["type"]: item["status"] for item in fields.get("conditions", [])}
            phase = fields.get("phase")
            if phase == "Succeeded":
                state = "completed"
            elif phase in {"Failed", "Pending"} or conditions.get("Ready") == "False":
                state = "attention"
            elif phase == "Running" and conditions.get("Ready") == "True":
                state = "healthy"
            observations.append({"uid": record.uid, "kind": record.kind, "namespace": record.namespace,
                                 "state": state, "phase": phase,
                                 "restarts": sum(item["restarts"] for item in fields.get("containers", []) if type(item.get("restarts")) is int),
                                 "waiting_reasons": [item["waiting_reason"] for item in fields.get("containers", []) if item.get("waiting_reason")]})
        elif record.kind == "Node":
            ready = next((item["status"] for item in fields.get("conditions", []) if item["type"] == "Ready"), None)
            state = "healthy" if ready == "True" else "attention" if ready == "False" else "unknown"
            observations.append({"uid": record.uid, "kind": record.kind, "namespace": None, "state": state})
        elif record.kind in {"Deployment", "ReplicaSet", "StatefulSet", "DaemonSet"}:
            desired = fields.get("desiredNumberScheduled") if record.kind == "DaemonSet" else fields.get("desired_replicas")
            ready = fields.get("numberReady") if record.kind == "DaemonSet" else fields.get("readyReplicas", 0)
            if desired is not None:
                state = "healthy" if ready >= desired else "attention"
            if fields.get("generation", 0) > fields.get("observed_generation", 0):
                state = "unknown"
            observations.append({"uid": record.uid, "kind": record.kind, "namespace": record.namespace,
                                 "state": state, "desired": desired, "ready": ready})
    return {"observations": observations, "partial": snapshot.partial, "historical_metrics_available": False}


def posture(snapshot: Snapshot) -> dict:
    validate_scope(snapshot)
    findings = []

    def finding(record, code, severity, qualifier=None):
        findings.append({"object_uid": record.uid, "kind": record.kind, "namespace": record.namespace,
                         "code": code, "severity": severity, "qualifier": qualifier,
                         "observed_at": record.observed_at.isoformat()})

    complete = {(item.kind, item.namespace) for item in snapshot.coverage if item.state == "complete"}
    policies = [record for record in snapshot.objects if record.kind == "NetworkPolicy"]
    for record in snapshot.objects:
        fields = record.fields.get("pod_template", record.fields)
        if record.kind in {"Pod", "Deployment", "ReplicaSet", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
            for key in ("host_network", "host_pid", "host_ipc"):
                if fields.get(key):
                    finding(record, key, "high")
            for container in fields.get("containers", []):
                if container.get("privileged"):
                    finding(record, "privileged_container", "high", container.get("name"))
                if container.get("allow_privilege_escalation") is True:
                    finding(record, "privilege_escalation_enabled", "medium", container.get("name"))
            if record.kind == "Pod" and ("NetworkPolicy", record.namespace) in complete:
                applicable = [policy for policy in policies if policy.namespace == record.namespace]
                # This is only a missing-policy indicator, never proof of packet
                # isolation or CNI policy enforcement. Expressions remain unknown.
                if not applicable:
                    finding(record, "namespace_has_no_network_policy", "medium", "configuration_indicator_only")
        elif record.kind in {"Role", "ClusterRole"}:
            if any("*" in rule.get(key, []) for rule in record.fields.get("rules", []) for key in ("verbs", "resources", "apiGroups")):
                finding(record, "wildcard_rbac", "high")
        elif record.kind in {"RoleBinding", "ClusterRoleBinding"}:
            if record.fields.get("role_ref") == {"kind": "ClusterRole", "name": "cluster-admin"}:
                finding(record, "cluster_admin_binding", "high")
        elif record.kind == "Service":
            if record.fields.get("service_type") in {"LoadBalancer", "NodePort"} or record.fields.get("has_external_endpoint"):
                finding(record, "potential_external_service", "medium", "reachability_unverified")
        elif record.kind == "ServiceAccount" and record.fields.get("automount_service_account_token") is True:
            finding(record, "service_account_token_automount_enabled", "low", "configuration_indicator_only")
    return {"findings": findings, "coverage": [{"kind": item.kind, "namespace": item.namespace, "state": item.state} for item in snapshot.coverage],
            "assessment": "partial" if snapshot.partial else "bounded_checks_complete", "formal_compliance": False}
