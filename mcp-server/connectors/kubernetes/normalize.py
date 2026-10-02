"""Explicit field projection; raw manifests/annotations/env/messages never persist."""

from .models import CollectionError, ObjectRecord, Resource


LABELS = frozenset({"app", "team", "owner", "app.kubernetes.io/name", "app.kubernetes.io/instance", "app.kubernetes.io/part-of"})


def strings(values) -> list[str]:
    return [item for item in values if isinstance(item, str) and len(item) <= 512] if isinstance(values, list) else []


def labels(value) -> dict[str, str]:
    return {key: val for key, val in value.items() if key in LABELS and isinstance(val, str) and len(val) <= 255} if isinstance(value, dict) else {}


def pod_fields(spec: dict, status: dict) -> dict:
    containers = []
    statuses = {item.get("name"): item for field in ("containerStatuses", "initContainerStatuses", "ephemeralContainerStatuses") for item in status.get(field, [])}
    for field in ("containers", "initContainers", "ephemeralContainers"):
        for container in spec.get(field, []):
            security = container.get("securityContext", {})
            current = statuses.get(container.get("name"), {})
            state = current.get("state", {})
            # No arbitrary provider message, command/args, env, mount paths or
            # Secret/config-map contents. Image refs and security flags only.
            containers.append({
                "name": container.get("name", ""), "image": container.get("image", ""),
                "privileged": security.get("privileged") is True,
                "allow_privilege_escalation": security.get("allowPrivilegeEscalation"),
                "run_as_non_root": security.get("runAsNonRoot"),
                "ready": current.get("ready"),
                "restarts": current.get("restartCount", 0),
                "waiting_reason": state.get("waiting", {}).get("reason"),
            })
    return {
        "containers": containers, "node_name": spec.get("nodeName"),
        "service_account": spec.get("serviceAccountName", "default"),
        "automount_service_account_token": spec.get("automountServiceAccountToken"),
        "host_network": spec.get("hostNetwork") is True,
        "host_pid": spec.get("hostPID") is True, "host_ipc": spec.get("hostIPC") is True,
        "phase": status.get("phase"),
        "claims": [volume["persistentVolumeClaim"]["claimName"] for volume in spec.get("volumes", [])
                   if isinstance(volume.get("persistentVolumeClaim"), dict)
                   and isinstance(volume["persistentVolumeClaim"].get("claimName"), str)],
    }


def normalize(raw: dict, resource: Resource, namespace, connection, observed_at) -> ObjectRecord:
    if not isinstance(raw, dict):
        raise CollectionError("invalid_response")
    metadata = raw.get("metadata", {})
    if (not isinstance(metadata, dict) or raw.get("kind") != resource.kind
            or metadata.get("namespace") != namespace
            or not all(isinstance(metadata.get(key), str) and 0 < len(metadata[key]) <= 512
                       for key in ("uid", "name", "resourceVersion"))):
        raise CollectionError("invalid_response")
    spec, status = raw.get("spec", {}), raw.get("status", {})
    if not isinstance(spec, dict) or not isinstance(status, dict):
        raise CollectionError("invalid_response")
    try:
        fields = {
            "labels": labels(metadata.get("labels")),
            "owners": [{"uid": owner["uid"], "kind": owner["kind"]} for owner in metadata.get("ownerReferences", [])
                       if isinstance(owner, dict) and isinstance(owner.get("uid"), str)
                       and isinstance(owner.get("kind"), str)],
            "conditions": [{"type": condition["type"], "status": condition["status"]}
                           for condition in status.get("conditions", [])
                           if isinstance(condition, dict) and isinstance(condition.get("type"), str)
                           and condition.get("status") in ("True", "False", "Unknown")],
        }
        for key, value in (("generation", metadata.get("generation")), ("observed_generation", status.get("observedGeneration"))):
            if type(value) is int:
                fields[key] = value
        if resource.kind == "Pod":
            fields.update(pod_fields(spec, status))
        elif resource.kind in {"Deployment", "ReplicaSet", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
            template = spec.get("jobTemplate", {}).get("spec", {}) if resource.kind == "CronJob" else spec
            fields["pod_template"] = pod_fields(template.get("template", {}).get("spec", {}), {})
            for key in ("replicas", "readyReplicas", "availableReplicas", "desiredNumberScheduled", "numberReady", "active", "failed", "succeeded"):
                if type(status.get(key)) is int:
                    fields[key] = status[key]
            if type(spec.get("replicas")) is int:
                fields["desired_replicas"] = spec["replicas"]
        elif resource.kind == "Node":
            fields["provider_id"] = spec.get("providerID")
        elif resource.kind == "Service":
            fields.update({"service_type": spec.get("type", "ClusterIP"),
                           "selector": {key: val for key, val in spec.get("selector", {}).items() if isinstance(val, str)},
                           "has_external_endpoint": bool(status.get("loadBalancer", {}).get("ingress") or spec.get("externalIPs"))})
        elif resource.kind == "PersistentVolumeClaim":
            fields["volume_name"] = spec.get("volumeName")
            fields["phase"] = status.get("phase")
        elif resource.kind == "PersistentVolume":
            claim = spec.get("claimRef", {})
            fields["claim"] = {key: claim[key] for key in ("namespace", "name", "uid") if isinstance(claim.get(key), str)}
        elif resource.kind == "Event":
            reference = raw.get("involvedObject", {})
            fields.update({"event_type": raw.get("type"), "reason": raw.get("reason"),
                           "involved_uid": reference.get("uid"), "count": raw.get("count", 1)})
        elif resource.kind in {"Role", "ClusterRole"}:
            fields["rules"] = [{key: strings(rule.get(key)) for key in ("verbs", "resources", "apiGroups")}
                               for rule in raw.get("rules", []) if isinstance(rule, dict)]
        elif resource.kind in {"RoleBinding", "ClusterRoleBinding"}:
            ref = raw.get("roleRef", {})
            fields["role_ref"] = {key: ref.get(key) for key in ("kind", "name")}
        elif resource.kind == "ServiceAccount":
            fields["automount_service_account_token"] = raw.get("automountServiceAccountToken")
        elif resource.kind == "NetworkPolicy":
            fields["pod_selector"] = {key: value for key, value in spec.get("podSelector", {}).get("matchLabels", {}).items() if isinstance(value, str)}
            # matchExpressions require fuller policy evaluation; preserve that
            # limitation instead of claiming a match based only on labels.
            fields["selector_has_expressions"] = bool(spec.get("podSelector", {}).get("matchExpressions"))
            fields["policy_types"] = strings(spec.get("policyTypes"))
        # Reject malformed scalar fields rather than propagating nested values
        # through status/image/name fields into evidence or diagnostics.
        containers = fields.get("containers", fields.get("pod_template", {}).get("containers", []))
        for container in containers:
            for key in ("name", "image", "waiting_reason"):
                if container.get(key) is not None and not isinstance(container[key], str):
                    raise CollectionError("invalid_response")
            for key in ("allow_privilege_escalation", "run_as_non_root", "ready"):
                if container.get(key) is not None and type(container[key]) is not bool:
                    raise CollectionError("invalid_response")
            if type(container.get("restarts")) is not int or container["restarts"] < 0:
                raise CollectionError("invalid_response")
        for key in ("phase", "node_name", "service_account", "provider_id", "volume_name", "event_type", "reason", "involved_uid", "service_type"):
            if fields.get(key) is not None and not isinstance(fields[key], str):
                raise CollectionError("invalid_response")
        return ObjectRecord(connection.tenant_id, connection.cluster_id, metadata["uid"], resource.kind,
                            namespace, metadata["name"], metadata["resourceVersion"], observed_at, fields)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise CollectionError("invalid_response") from None
