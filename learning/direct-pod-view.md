# Guide 3 — The direct pod view: a second path that does not need the agent (S1.6)

Read [guide 1](mcp+observability-bootstrap.md) (evidence, ServiceAccounts, RBAC) and [guide 2](chat-graph.md) (the chat) first. This guide covers the Kubernetes page: a table of pods that Vyom reads by itself, with no model and no MCP.

Where the samples come from:

- **Real**: the Table columns, cells and metadata keys in section 3 were captured from the Kind cluster on 2026-10-13. The PASS lines are from your run of `pods-check.sh` the same day.
- **Illustrative**: the evidence JSON is shortened.

Section 8 has questions to answer out loud.

---

## 1. The whole thing in plain words

Guide 2 built one way to learn about pods: ask the agent. That way passes through a language model and an MCP server, and either can be down, slow or wrong.

This guide builds a second way that uses neither. Every 15 seconds the Kubernetes page asks the backend for the pod list. The backend asks the Kubernetes API directly, with its own read-only identity, and returns the result as **the same kind of evidence object** the agent path produces.

**An analogy.** A cockpit has an autopilot and it has plain instruments. The altimeter does not depend on the autopilot; if the autopilot fails you still know your height. And when both work, you can compare them: if the autopilot says one thing and the altimeter another, you have learned something important. The chat is the autopilot. This table is the altimeter.

Two things follow from that picture and they are the acceptance criteria of S1.6:

1. **Independence.** The table must keep working when MCP or the model is down.
2. **Agreement.** When both paths work, they must describe the same pod with the same identity, so their answers can be compared.

---

## 2. Two paths, side by side

The constitution calls these the "two execution paths". Keep this table in mind for the rest of the project; every later feature (EC2 in S2, cost in S4) has the same two columns.

| | Agent path (guide 2) | Direct path (this guide) |
|---|---|---|
| Used for | Exploring: a question in words | Showing: a table, a count, later a chart |
| Who decides what to read | The model proposes, the host checks | Code. Always the same read |
| Goes through | Model → MCP host → proxy → MCP server → Kubernetes API | Collector → Kubernetes API |
| Kubernetes identity | `kubernetes-mcp` (the MCP server's) | `vyom-collector` |
| Code | `agent/graph.py`, `mcp_client/` | `collectors/kubernetes.py` |
| Result | `Evidence` with `path: "mcp"` | `Evidence` with `path: "direct"` |
| Can fail because | Model, MCP server, proxy, token, Kubernetes | Token, Kubernetes |

What they share is **only** the evidence contract (`evidence.py`) and the trusted context. They do not share a client, a credential or a code path. That is deliberate: two paths that share a client are one path with two names, and they fail together.

One rule connects them: a success on one path is never counted as a success on the other. If MCP is down, the chat says so; it does not quietly fall back to this collector. If the collector is down, the table says so; it does not ask the agent.

---

## 3. Asking Kubernetes for less

### 3.1 The simple version

Kubernetes has an HTTP API. Listing pods is one GET:

```
GET /api/v1/namespaces/demo/pods
Authorization: Bearer <a ServiceAccount token>
```

That is the same request `kubectl get pods -n demo` makes. So the collector is, at heart, one authenticated HTTP request.

### 3.2 The problem with the simple version

By default that request returns every pod **in full**: the whole spec, including container images, commands, and literal environment variables. The demo `web` pod carries one on purpose:

```yaml
env:
  - name: DEMO_LITERAL_ENV
    value: vyom-demo-literal-env-value
```

Vyom's rule is that literal environment values never reach the model, the UI, history or telemetry. If the collector downloaded full pods and then picked out four fields, the secret-shaped data would still pass through the backend's memory, and one careless log line would leak it.

A second problem: the Status that `kubectl` prints (`ImagePullBackOff`, `CrashLoopBackOff`, `Terminating`) is **not a field** on the pod. It is computed from several fields by a piece of logic. If Vyom recomputed it, it would sooner or later disagree with kubectl.

### 3.3 The better version: ask for the table

The API server can do both jobs itself. Ask for a different representation with the `Accept` header, and ask for metadata only:

```
GET /api/v1/namespaces/demo/pods?limit=100&includeObject=Metadata
Accept: application/json;as=Table;g=meta.k8s.io;v=v1
```

Now the server sends a `Table`: column definitions, and one row per pod with the cells already computed. This is exactly what `kubectl get pods` asks for; kubectl just prints the cells. Captured from the Kind cluster:

```
columns : Name, Ready, Status, Restarts, Age, IP, Node, Nominated Node, Readiness Gates
cells   : broken-57f448799-h669z, 0/1, ImagePullBackOff, 0, 22h, 10.244.0.5, vyom-control-plane, <none>, <none>
object  : kind PartialObjectMetadata
          metadata keys: creationTimestamp, generateName, generation, labels, managedFields,
                         name, namespace, ownerReferences, resourceVersion, uid
          spec present: no
```

`includeObject=Metadata` attaches to each row the pod's metadata (name, namespace, **uid**) and nothing else. There is no spec in the response, so there is no environment value in it. The data Vyom must not handle never leaves the API server.

Your `pods-check.sh` run confirmed it against the real response: *"what the API server sends the collector has no pod spec and no literal env value (8038 bytes for 2 pods)"*.

The lesson is general and worth remembering: **the safest place to drop data is before it is sent to you.** Guide 1 made the same move on the MCP path by keeping the upstream's `list_output = "table"`.

**Where this stops being enough.** The Table carries only what `kubectl get pods` shows. S2.3 needs waiting and termination *reasons*, which are not in it. That task will need a second, carefully projected request. It is recorded as the consequence of decision K8S01.

### 3.4 Paging

A namespace can have thousands of pods. `limit=100` asks for the first hundred; if there are more, the response's metadata has a `continue` token, and the next request sends it back. The collector follows it for at most 20 pages and stops at 500 items (`max_items`). Past that, the evidence is cut and marked `truncated`, state `partial`. A list that silently stops at 500 would be a lie; one that says "partial" is not.

---

## 4. A separate identity

The three objects below are written in `deploy/chart/vyom/templates/identities.yaml` since S1.7 (they were `deploy/collector/rbac.yaml` when this guide was written):

```yaml
kind: ServiceAccount        # vyom-collector, in namespace vyom
kind: Role                  # in namespace demo: pods, verbs [list]
kind: RoleBinding           # gives that Role to vyom-collector
```

That is the entire permission: `list` on `pods` in `demo`. Not `get` (one pod by name), not `watch`, not logs, not exec, not Secrets, not another namespace, not nodes. (The Table request is a `list`.)

There are now three identities in play. Being able to say what each one is for is most of understanding the security model:

| Identity | Used by | May do |
|---|---|---|
| `kubernetes-mcp` | The MCP server pod, when it reads Kubernetes | `list` pods in `demo`; create TokenReviews and SubjectAccessReviews (for its proxy) |
| `vyom-api` | The backend, when it talks to the **MCP endpoint** | Nothing in the Kubernetes API. Only "may call the MCP endpoint" |
| `vyom-collector` | The backend's collector, when it talks to the **Kubernetes API** | `list` pods in `demo` |

Why not reuse one? Because each credential should open exactly one door. Your live run shows the doors are really separate: *"an invalid token, and the token the backend presents to the MCP endpoint, are both refused by the Kubernetes API: denied / auth"*. The MCP-endpoint token has the wrong audience for the Kubernetes API (guide 1, section 2.7).

Ask the cluster yourself:

```sh
kubectl --context kind-vyom auth can-i list pods -n demo        --as=system:serviceaccount:vyom:vyom-collector   # yes
kubectl --context kind-vyom auth can-i get pods -n demo         --as=system:serviceaccount:vyom:vyom-collector   # no
kubectl --context kind-vyom auth can-i list pods -n kube-system --as=system:serviceaccount:vyom:vyom-collector   # no
kubectl --context kind-vyom auth can-i list secrets -n demo     --as=system:serviceaccount:vyom:vyom-collector   # no
```

**The open question (K8S02).** On your machine `dev-up.sh` gets the collector's token with `kubectl create token vyom-collector`. In the cluster (S1.7) the backend is a pod, and a pod has exactly **one** ServiceAccount, which today is `vyom-api`. So how does one pod hold a second identity? Three options, none chosen yet:

1. Mount a token Secret for `vyom-collector` into the pod. Identities stay separate; the token is long-lived.
2. Give the read permission to `vyom-api`. Simplest; but then the MCP-facing identity can read Kubernetes directly, which `mcp-check.sh` currently asserts it cannot.
3. Run the collector as its own workload with its own ServiceAccount. Cleanest; adds a Deployment and an internal API.

This is a real trade-off between separation and simplicity, and it is yours to decide before S1.7 starts.

---

## 5. Reading the code

All in `backend/src/vyom/`.

### 5.1 `collectors/kubernetes.py`

Read it top to bottom; it is about 200 lines.

**`KubernetesApiConfig`** is what the operator may configure:

| Field | Meaning | Guard |
|---|---|---|
| `connection_id` | Which authorized connection this API server belongs to | Must equal the trusted context's, or `scope_violation` |
| `url` | The API server root | `https` only, no path, no credentials in it |
| `ca_file` | The certificate to trust | |
| `credential_ref` | `file:/path` or `env:NAME`, never the token | Same `check_reference` as everywhere else |
| `timeout_seconds`, `max_response_bytes`, `max_items` | Bounds | Each has an upper limit |

You have seen every one of these ideas in `ServerConfig` (guide 1, section 4.1). It is the same discipline applied to a different endpoint.

**`PodCollector.collect(context)`** has the same skeleton as `McpHost.call`:

1. Open a span, `collector.kubernetes.pods`.
2. Check the connection matches the context.
3. `_list`: read the token, make the client (`trust_env=False`, the CA, a timeout), fetch pages.
4. Catch anything, turn it into an `ErrorKind` with `_classify`. Only the exception's type or the HTTP status is used, never its text.
5. `build_evidence(path="direct", collector="kubernetes-pods", …)`.
6. `telemetry.record_collector_run(...)`.

Like `host.call`, it never raises for an expected failure. It always returns evidence.

**`_page`** streams the response and counts bytes, stopping at `max_response_bytes` (`oversized`). Same idea as `_GuardedTransport` in the host.

**`_drafts`** turns one Table page into item drafts. It finds columns **by name**, not by position:

```python
names = [column["name"] for column in table["columnDefinitions"]]
index = {name: names.index(name) for name in ("Name", "Ready", "Status", "Restarts")}
```

So if a future Kubernetes version inserts a column, nothing shifts. If a required column is missing, `names.index` raises, and the caller reports `invalid_output`. Wrong data is never guessed at.

Restarts arrives as text such as `1 (3h ago)`; `int(str(cell).split()[0])` keeps the number, the same normalisation the MCP path does.

One subtle behaviour: pages read **before** a failure are kept. If page 1 succeeds and page 2 gets a 500, the evidence has page 1's pods, an `unavailable` error, and state `partial`. That is more honest than either throwing away good data or presenting half a list as whole.

### 5.2 How failures map

| What happened | Error kind | State |
|---|---|---|
| HTTP 401, or the token could not be read | `auth` | `denied` |
| HTTP 403 (RBAC says no) | `forbidden` | `denied` |
| Could not connect, HTTP 5xx | `unavailable` | `missing` |
| Timed out | `timeout` | `missing` |
| Response is not the expected shape | `invalid_output` | `missing` |
| A page is larger than the byte limit | `oversized` | `missing` |
| Context is for another connection; or a row from another namespace | `scope_violation` | `denied` |
| More than `max_items` | `truncated` | `partial` |
| Read worked, no pods | none | `zero` |

Compare this with the table in guide 1, section 2.6. Same kinds, same states. A reader of evidence does not need to know which path produced it to know what it may conclude.

### 5.3 The same pod, the same ID

The agent path and this path both call `build_evidence`, which builds the item ID from fields both can supply:

```
k8s:<cluster uid>:<namespace>:<kind>:<name>
k8s:…:demo:pod:broken-57f448799-h669z
```

The direct path also has the pod's **UID** (from the metadata); the MCP table does not carry one. So the UID sits beside the ID as extra information, and is not part of it. If the ID included the UID, the two paths could never match. (Decision MCPC04.)

This is what lets the live check say: *"a fresh MCP-backed answer names and cites the new pod; every citation is a row of the direct table."* The citation's `item_id` from the chat and the row's `id` from the table are the same string.

### 5.4 The route

In `api/app.py`:

```python
@app.get("/api/kubernetes/pods")
async def kubernetes_pods() -> PodsView:
    if pods is None or resolver is None:
        return PodsView(configured=False)
    return PodsView(configured=True, evidence=await pods.collect(resolver.resolve()))
```

- `PodsView` is `{configured, evidence}`. `evidence` is absent only when no collector is configured. A *failed* read is evidence with an error in it, not a missing field and not an HTTP error. Same reasoning as "every chat outcome is 200".
- Nothing is cached. Each request reads the cluster. For one person and one namespace that is the simplest thing that is always fresh. Scheduled collection and stored history arrive in S3.6.
- The namespace comes from `resolver.resolve()`. The route takes no parameters at all.

### 5.5 Configuration

The operator file gained one optional section (`mcp_client/registry.py`):

```json
"kubernetes": {
  "connection_id": "kind-vyom",
  "url": "https://127.0.0.1:41425",
  "ca_file": "/…/.local/dev-kubernetes-ca.crt",
  "credential_ref": "file:/…/.local/dev-collector-token"
}
```

Each section of the file switches one surface on: `mcp_servers` and `model` together enable chat; `kubernetes` enables the table. Leave one out and that surface reports "not configured" while the other keeps working. Look at `.local/operator.json` after running `dev-up.sh` to see a complete one (it contains references to credentials, no credentials).

---

## 6. Telemetry for something that runs on a timer

The chat is driven by a person, so "how did requests end" is the natural question. A collector runs whether or not anyone is looking, so the natural question is different: **is it still working, and how old is what I am looking at?**

| Metric | Type | Answers |
|---|---|---|
| `vyom_collector_runs_total{collector, outcome}` | counter | How do runs end? |
| `vyom_collector_duration_seconds{collector}` | histogram | How long does a run take? |
| `vyom_collector_last_success_timestamp_seconds{collector}` | **gauge** | When did it last work? |

The third is the project's first gauge. A counter can only tell you a rate; it cannot tell you "nothing has succeeded for ten minutes" in a way that is easy to alert on. A timestamp can:

```
time() - vyom_collector_last_success_timestamp_seconds{collector="kubernetes-pods"}
```

is "seconds since the last good run". It is absent until the first success, which is itself the "unavailable is not zero" rule: no success yet is not the same as a success at time zero.

Labels: `collector` is a fixed name in code (`kubernetes-pods`); `outcome` is `ok` or an error kind. Bounded. No pod name or UID appears in any span, log line or metric; your run checked 46 spans and 23 log lines.

---

## 7. The controlled change: how the acceptance was proven

"A controlled workload change appears in the direct table and in an independent MCP answer, with matching identity." Here is what `scripts/pods-check.sh` does to prove it, step by step, with your results:

1. Reads the table and compares it with `kubectl -n demo get pods`, including UIDs. *2 pods, equal.*
2. Reads the same namespace through the MCP host and compares IDs and values with the table. *Equal.*
3. Points the configuration at a dead MCP address and reads the table again. *Still complete.* (Independence.)
4. Runs `kubectl scale deployment/web --replicas=2`. This is the script changing the demo workload with **your** kubectl access. Vyom itself cannot do it; it has no write permission anywhere.
5. Reads the table again. *3 pods, a new collection ID, a later collection time.*
6. Reads through MCP again. *The new pod is there under the same ID.*
7. Asks the agent "List every pod in the demo namespace with its status." *The answer names and cites the new pod, and every citation is a row of the table.* (Agreement.)
8. Scales back to 1 and waits for the table to follow. *2 pods.*
9. Tries the failures: a namespace it may not read, a bad token, the wrong kind of token, an unreachable API. *Each one explicit, none of them an empty list.*

A detail worth understanding in step 8: when a Deployment scales down, the removed pod does not vanish. It shows as `Terminating` for its grace period (30 seconds by default). Both kubectl and the table show it during that time, because both get the status from the same server-side computation. The script waits for the count to drop before comparing.

---

## 8. Say it back

<details><summary>1. In plain words: why does Vyom read pods in two different ways?</summary>

One way is for asking questions in words and goes through a model. The other is for showing a table and is plain code. The second must not depend on the first, so that when the model or MCP is down you can still see your cluster, and so that you have something independent to check the agent's answers against.
</details>

<details><summary>2. Why does the collector ask for a Table, and not for the pods themselves?</summary>

Two reasons. Full pod objects contain specs with literal environment values, which Vyom must never handle; with a Table plus metadata only, the API server never sends them. And the Status that people recognise from kubectl is computed by the server for the Table; asking for it means Vyom's status always equals kubectl's.
</details>

<details><summary>3. The collector's RoleBinding is deleted. What does the Kubernetes page show, and why is that better than an empty table?</summary>

The API answers 403, the collector reports `forbidden`, the evidence state is `denied`, and the page shows "The source denied access to the requested resources" with no rows. An empty table would say "there are no pods", which is a statement about the cluster. `denied` says "I was not allowed to look", which is a statement about Vyom. Confusing them would turn a permissions problem into false good news.
</details>

<details><summary>4. The MCP server is down. What still works, what does not, and what does Vyom refuse to do?</summary>

The Kubernetes page works; it does not touch MCP. Chat does not: it ends `no_evidence` with error `unavailable`. What Vyom refuses to do is answer the chat question from the collector's data and present that as an agent answer. The paths are independent in both directions.
</details>

<details><summary>5. Why is the pod's UID not part of its ID, when a UID is the most precise identifier Kubernetes has?</summary>

Because the ID has to be buildable by both paths, and the MCP path's table has no UID. An ID made of cluster, namespace, kind and name is the same string on both paths, which is what makes a citation from the chat match a row in the table. The UID is carried next to it where available, to tell apart two pods that had the same name at different times.
</details>

<details><summary>6. What does <code>vyom_collector_last_success_timestamp_seconds</code> let you ask that the run counter does not?</summary>

"How long since it last worked?" as a single number: `time()` minus the gauge. With only a counter of successes you would have to notice the *absence* of increase over a window. Staleness is the main question for anything that collects on a schedule.
</details>

---

## 9. Try it

With `./scripts/dev-up.sh` running (see [README](README.md#run-the-app)):

```sh
# The table as the API returns it
curl -s 127.0.0.1:8000/api/kubernetes/pods | python3 -m json.tool

# Compare with kubectl, by eye
kubectl --context kind-vyom -n demo get pods

# Watch a change arrive: open http://127.0.0.1:5173/kubernetes, then
kubectl --context kind-vyom -n demo scale deployment/web --replicas=2
#   within 15 seconds a third row appears; then put it back:
kubectl --context kind-vyom -n demo scale deployment/web --replicas=1
#   the removed pod shows as Terminating for about 30 seconds before it disappears

# See "denied" for yourself, then repair it
kubectl --context kind-vyom -n demo delete rolebinding vyom-collector-pod-reader
curl -s 127.0.0.1:8000/api/kubernetes/pods | python3 -m json.tool      # state "denied", error "forbidden"
./scripts/vyom-up.sh     # re-applies the chart, including the RoleBinding

# Collector metrics after those reads
curl -s 127.0.0.1:8000/metrics | grep vyom_collector
```

The rules as tests:

```sh
cd backend && uv run pytest tests/test_pod_collector.py -v
```

An exercise: in `_drafts`, change `"Status"` to `"Phase"` in the column tuple, run the tests, and read which state the evidence ends in and why. Restore it.
