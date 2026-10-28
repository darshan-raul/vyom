# Guide 1 — MCP and observability: the foundations (S1.1–S1.4, S1.9)

A study note, kept with the other learning material in `learning/`. This is the first of four guides; [README.md](README.md) has the reading order. It covers the pieces built in S1.1, S1.9, S1.2, S1.3 and S1.4: the MCP host, the upstream Kubernetes MCP server, the model adapter and the telemetry rules. Guides 2–4 build on it: [the chat](chat-graph.md) (S1.5), [the direct pod view](direct-pod-view.md) (S1.6) and [the frontend](frontend-console.md). Updated 2026-10-13, after S1.6.

How to use it: read Part 1 for the map, Parts 2 and 3 for the two topics that are new to you, then follow Part 4 with the files open. Part 5 has things to run so you can see each idea happen. Parts 2 and 3 each end with questions to answer out loud; if you cannot explain an answer in your own words without looking, that is the section to reread.

Where the samples come from:

- **Real output**: the tool descriptor in 2.5, the evidence object in 2.6, the metric lines in 3.2 and the log lines in 3.3 were produced by running this repository's code while writing the guide.
- **Illustrative**: the JSON-RPC messages in 2.3 and the `traceparent` header in 3.4 show the general shape from the specifications. I did not capture them from this stack, and exact fields vary by protocol version.

---

## Part 1 — What exists right now

This guide is about four pieces. Since S1.5 they are joined into a chat by a small LangGraph workflow ([guide 2](chat-graph.md)), and since S1.6 a second, independent path reads pods directly ([guide 3](direct-pod-view.md)). Here they are on their own:

```
                (guide 2: LangGraph + POST /api/chat sit here)
                         |                     |
                         v                     v
   ModelClient (S1.4)                     McpHost (S1.2)
   agent/model.py                         mcp_client/host.py
        |                                      |
        | HTTPS, bearer API key                | HTTPS, bearer ServiceAccount token
        v                                      v
   OpenRouter -> Claude Haiku 5.5         kube-rbac-proxy  --->  kubernetes-mcp-server (S1.3)
                                          (who is calling?)      (lists pods as its own identity)
                                                                        |
                                                                        v
                                                                 Kubernetes API (namespace demo)

   Everything above emits: logs + metrics + spans      (telemetry.py, S1.9)
   Collected on Kind by:   Alloy -> Loki / Tempo, Prometheus, shown in Grafana   (S1.9)
```

| Task | In one sentence | Proven how |
|---|---|---|
| S1.1 | Empty but working React UI and FastAPI backend with a health endpoint | Local run, CI |
| S1.9 | Prometheus, Loki, Tempo, Alloy, Grafana on Kind, and the backend's telemetry rules | Live on Kind |
| S1.2 | The evidence format and the MCP host (the gatekeeper for tool calls) | Fixture server |
| S1.3 | The real upstream Kubernetes MCP server on Kind, one pod-list tool | Live on Kind |
| S1.4 | The model adapter (LangChain `ChatOpenAI` to OpenRouter) | Live, your run |

Two things to keep in mind while reading:

- When this guide was first written the API had only `/api/health`. It now also has `/api/chat`, `/api/agent` (guide 2) and `/api/kubernetes/pods` (guide 3). The host and the model adapter described here did not change when those were added; that is the point of having them as separate pieces.
- Prometheus does not scrape the backend yet (the backend is not deployed in the cluster until S1.7), so backend metrics exist in the process but not in Grafana. For the same reason there are no `vyom-api` logs in Loki yet; the only Vyom-related logs there come from the MCP pod.

One sentence that explains most design choices in the code: **the model and the MCP server are both treated as untrusted, and telemetry is treated as a place secrets must never reach.** Parts 2 and 3 are those two ideas in detail.

---

## Part 2 — MCP, taught from what you already know

### 2.1 The idea, by analogy with LangChain

In LangChain you write a Python function, wrap it as a tool, and `bind_tools` hands its name, description and argument schema to the model. The model replies with a tool call; your code runs the function.

```python
@tool
def list_pods(label_selector: str | None = None) -> str:
    """List pods in the namespace."""
    return kubernetes_client.list_namespaced_pod(...)   # runs in YOUR process, with YOUR credentials

model.bind_tools([list_pods])
```

MCP (Model Context Protocol) moves the function out of your process. The tool lives in a separate **server**. Your program talks to it over a network protocol and asks two things: "what tools do you have?" and "run this tool with these arguments".

| LangChain idea | MCP equivalent |
|---|---|
| A Python tool function | A tool on an MCP **server** (another process, possibly written by someone else) |
| The tool's name, description, args schema | What the server returns from `tools/list` (`name`, `description`, `inputSchema`) |
| Calling the function | A `tools/call` request |
| The function's return value | A result with `content` blocks (usually text), optional `structuredContent`, and an `isError` flag |
| An exception in the function | Either a protocol error, or a normal result with `isError: true` and an error text |

What stays the same: the model still only ever sees a name, a description and a JSON schema, and still only ever emits a proposed call. MCP does not change the model side at all. In Vyom the model does not know MCP exists.

What changes:

- **Who wrote the tool.** The Kubernetes tools are written and maintained upstream (`containers/kubernetes-mcp-server`). Vyom writes none of the Kubernetes access code on this path.
- **Where the credentials live.** The MCP server holds the Kubernetes identity. The backend holds only a token that lets it talk to the MCP server.
- **What you can assume.** A local function does what you wrote. A remote server does what *it* decides, and tells you about itself in its own words. Section 2.5 is about that.

MCP also defines things other than tools (resources, prompts, and requests the server can send back to the client). Vyom uses tools only. The host checks that the server declared the tools capability and ignores everything else.

### 2.2 The three roles

```
   +-------------------- Vyom backend process --------------------+
   |  HOST  (McpHost)                                             |
   |   - knows which servers exist (operator config)              |
   |   - knows which tools are allowed (ToolSpec + enabled_tools) |
   |   - holds the credential references                          |
   |                                                              |
   |     CLIENT (mcp SDK Client) ----- one connection ----------------->  SERVER
   |     CLIENT (a second server would get its own client) ------------>  another SERVER
   +--------------------------------------------------------------+
```

- **Server**: exposes tools. Here: the upstream Kubernetes MCP server in the cluster.
- **Client**: one connection to one server. It speaks the protocol and nothing more. Here: the official Python `mcp` SDK's `Client`, built by `client_for` in `mcp_client/__init__.py`.
- **Host**: the application that owns the clients, decides which servers to connect to and which tools the model may use. Here: Vyom's `McpHost`.

The distinction matters because the protocol has no opinion about policy. The SDK client will happily call any tool the server has. Every rule about *which* tool, *which* arguments and *which* namespace lives in the host, which is why `host.py` is the largest file in the backend.

Vyom is a host and client only. It never serves MCP. That is a project rule ("no production MCP protocol server").

### 2.3 What travels on the wire

Messages are JSON-RPC 2.0. There are three kinds:

- a **request** has an `id` and a `method`, and expects exactly one response with the same `id`;
- a **response** carries either `result` or `error`;
- a **notification** has a `method` but no `id`, and gets no response.

Illustrative shape of the two calls Vyom makes:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}

{"jsonrpc":"2.0","id":2,"result":{"tools":[
  {"name":"pods_list_in_namespace",
   "description":"...text written by the server...",
   "inputSchema":{"type":"object","properties":{"namespace":{"type":"string"},"labelSelector":{"type":"string"}},"required":["namespace"]},
   "annotations":{"readOnlyHint":true}}
]}}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call",
 "params":{"name":"pods_list_in_namespace","arguments":{"namespace":"demo","labelSelector":"app=web"}}}

{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"NAMESPACE   APIVERSION   KIND   NAME ..."}],"isError":false}}
```

Two things to notice in that second pair:

- The result is **text**. For this server it is a fixed-width table, like `kubectl get pods -o wide`. Vyom has to parse it.
- A failing tool usually still returns a normal JSON-RPC `result`, with `isError: true` and a message in `content`. A JSON-RPC `error` is for protocol-level problems (unknown method, bad parameters).

Two transports exist:

- **stdio**: the host starts the server as a child process and talks over stdin/stdout. Common on a laptop, and what most tutorials show.
- **Streamable HTTP**: the server listens on one URL (here `/mcp`). The client POSTs each JSON-RPC message. The server answers either with plain JSON or with a `text/event-stream` body (server-sent events) that carries the response. This is what Vyom uses, because the server is a pod in the cluster.

Because a response can be a stream, the host has to limit size in two places: `max_sse_event_size` on the SDK client (one event) and `_GuardedTransport` on the HTTP layer (total bytes of the body). Both are set from the same `max_response_bytes`.

### 2.4 The lifecycle of one session

1. **initialize**: client and server agree on a protocol version (here `2026-07-28`) and exchange **capabilities** (what each side supports: tools, resources and so on) and names. The server says who it is (`kubernetes-mcp-server`, `v0.0.67`). Vyom records that in evidence as provenance; it does not use it for any decision.
2. **tools/list** (discovery): the server lists its tools. Long lists come in pages: a response may carry a `nextCursor`, which the client sends back to get the next page. `_advertised` in `host.py` follows cursors for at most 10 pages and then gives up with a `protocol` error, so a server cannot keep the host listing forever.
3. **tools/call**: the client names a tool and passes arguments.
4. Close.

Vyom opens a fresh session for every operation and closes it. Nothing (session, token, discovered schema) is kept between calls.

| What that costs | What it buys |
|---|---|
| A handshake and a `tools/list` on every call (a few extra round trips) | A rotated token is picked up on the next call |
| No streaming of updates from the server | A schema change is noticed on the very call it would affect |
| | No shared session state between two requests, which matters once there are several users (S6) |

The server is also configured `stateless = true`, so it keeps nothing per session on its side either.

### 2.5 The part most tutorials skip: an MCP server is not trusted

A typical tutorial does "connect, list tools, give them all to the model". Vyom deliberately does not. Four concrete ways that goes wrong, and what the code does about each:

| Risk | Example | Control in Vyom | Where |
|---|---|---|---|
| **The server describes itself** | A tool description contains "ignore previous instructions and…", or `readOnlyHint: true` on a tool that deletes | The model is shown Vyom's own description and schema. Upstream descriptions and annotations are never read for a decision and never shown to the model | `ToolSpec.description`, `McpHost.tools` |
| **The server changes after review** | An upgrade adds an argument, or a tool keeps its name and changes meaning | The reviewed input schema is stored as a SHA-256 digest; a different schema disables the tool (`schema_mismatch`) until someone reviews it | `schema_digest`, `_mismatch` |
| **The model chooses scope** | The model passes `namespace: kube-system` | Scope arguments are removed from what the model sees and filled in by the host from trusted config. A different value is refused before any network request | `_bind_arguments` |
| **Results are raw** | A pod row carries IP, node, labels; other tools return env values | The result is parsed and reduced to a few named fields; anything unexpected is discarded as `invalid_output` | `project_pod_table` |

A fifth, quieter one: **result text can itself contain instructions** ("pod name: ignore-your-rules…"). The projection reduces what gets through, and the project rule is that collected text is data, never instructions. What the answer step does about it (one tool call only, and an answer that must cite the evidence) is in [guide 2, section 4](chat-graph.md#4-what-stops-the-model-from-going-further-than-the-evidence).

**The three conditions.** A tool can be called only if all three hold:

1. Vyom has a reviewed definition for it in code (a `ToolSpec` in `kubernetes.py`),
2. the operator enabled it in configuration for that server (`enabled_tools`),
3. the server advertises it with exactly the input schema that was reviewed.

Conditions 1 and 2 are checked once, in `McpHost.__init__`. Condition 3 is checked on every call, on the same session, immediately before the call. Discovery (`McpHost.discover`) can report that a server has other tools; it never enables one.

**The digest.** `schema_digest` serialises the advertised `inputSchema` as JSON with sorted keys and no spaces, then takes SHA-256. Sorting keys makes it independent of the order the server happens to emit. The reviewed value sits in `kubernetes.py` as `input_schema_sha256`.

**The tool ID.** The model-facing name is `<server>__<tool>`, e.g. `kubernetes__pods_list_in_namespace`. Server IDs may not contain an underscore, so the double underscore always separates the two parts unambiguously, and two servers can have a tool with the same name.

**What the model is actually sent** (real output of `_wire_tool(host.tools()[0])`):

```json
{"type": "function",
 "function": {
  "name": "kubernetes__pods_list_in_namespace",
  "description": "List the pods in the configured namespace with readiness, status and restart count. Optionally filter with a Kubernetes label selector.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "labelSelector": {"anyOf": [{"maxLength": 253, "pattern": "^([/_.\\-A-Za-z0-9=, ()!])+$", "type": "string"}, {"type": "null"}],
                      "default": null, "title": "Labelselector"}},
   "title": "PodsListArguments", "type": "object"}}}
```

There is no `namespace` property. The upstream tool requires one; the host adds it. That is why, in your live run, the model "would not send" `namespace` or `fieldSelector`: they are not in the schema it was given. The host would refuse them anyway, which the offline tests prove.

**Four fences, not one.** The same restriction is applied at several independent places, so one mistake does not open the cluster:

| Fence | Says | If only this one existed |
|---|---|---|
| Host allowlist (`McpHost`) | Only `pods_list_in_namespace`, only namespace `demo` | A host bug could call any server tool |
| Server config (`config.toml`) | `read_only = true`, `enabled_tools = ["pods_list_in_namespace"]`, Secrets denied | A server bug could read anything its identity allows |
| Kubernetes RBAC | The server's ServiceAccount may `list pods` in `demo`, nothing else | This is the one enforced by Kubernetes itself |
| Endpoint authentication (proxy) | Only `vyom-api` with the right audience may talk to the server | Anything in the cluster could use the server |

`mcp-check.sh` tests each fence separately, including going *around* the host with a raw SDK client to confirm the server itself refuses delete, exec, log and Secret tools.

### 2.6 Evidence: what a tool call turns into

A tool result is never passed around raw. It becomes an `Evidence` object (`backend/src/vyom/evidence.py`). Here is a real one, built from the captured pod table in `backend/tests/data/`:

```json
{"id": "ev_e8ef4cf311904fd3a4b4bf81026d57c1",
 "source": {"path": "mcp", "workspace_id": "ws-local", "connection_id": "kind-vyom", "cluster_uid": "1111", "namespace": "demo",
            "mcp": {"server_id": "kubernetes", "tool_id": "kubernetes__pods_list_in_namespace",
                    "upstream_name": "kubernetes-mcp-server", "upstream_version": "v0.0.67", "protocol_version": "2026-07-28"},
            "collector": null},
 "collected_at": "2026-10-12T08:57:17.832073Z",
 "state": "complete",
 "coverage": {"complete": true, "returned": 2, "truncated": false},
 "items": [
  {"id": "k8s:1111:demo:pod:broken-57f448799-h669z", "kind": "Pod", "namespace": "demo", "name": "broken-57f448799-h669z",
   "uid": null, "observed_at": null, "attributes": {"ready": "0/1", "status": "ImagePullBackOff", "restarts": 0}},
  {"id": "k8s:1111:demo:pod:web-769fb547f5-kxxc6", "kind": "Pod", "namespace": "demo", "name": "web-769fb547f5-kxxc6",
   "uid": null, "observed_at": null, "attributes": {"ready": "1/1", "status": "Running", "restarts": 4}}],
 "errors": []}
```

Compare it with the table it came from. The row had IP, node, age and labels; none are here. The upstream wrote `4 (2m ago)` for restarts; evidence has the integer `4`.

Reading the fields:

| Field | Answers | Note |
|---|---|---|
| `source` | Who was asked, and under which authority | Scope fields are copied from the trusted context, not from the result |
| `source.mcp` | Which server, tool and upstream version | What the server said about itself; recorded, not trusted |
| `collected_at` | When | Set by the host. `observed_at` on an item is the source's own timestamp and is never invented (here the table has none) |
| `state` | What a reader may conclude | See below |
| `coverage` | How much of the answer is here | `truncated` is true when cut at `max_items` |
| `items[].id` | A stable identity for citing | `k8s:<cluster_uid>:<namespace>:<kind>:<name>`. The same pod gets the same ID whether it came through MCP or (from S1.6) the direct SDK path |
| `errors` | What went wrong | Kind plus a fixed message |

**The six states.**

| State | Meaning | Example |
|---|---|---|
| `complete` | The source answered in full, with items | 2 pods listed |
| `zero` | The source answered in full: nothing matches | selector matched no pods |
| `partial` | Some of the answer is missing | cut at the item limit |
| `stale` | Collected too long ago for this reader | computed at read time by `state_at` |
| `denied` | Refused by policy or by the source | wrong namespace, bad token, RBAC |
| `missing` | No observation at all | unreachable, timeout, oversized |

The point: "there are no unhealthy pods" (`zero`) must never be confused with "I could not look" (`missing`) or "I was not allowed to look" (`denied`). An agent that mixes these up gives confident wrong answers. A model handed an empty list will say "everything is healthy"; a model handed `state: missing` can say "I could not reach the cluster".

**How the state is decided** (the last block of `build_evidence`, in order):

1. There is an error other than `truncated`, and no items → `denied` if any error is a refusal (`tool_not_allowed`, `scope_violation`, `auth`, `forbidden`), otherwise `missing`.
2. Otherwise, not complete (any error at all, or the path said so) → `partial`.
3. Otherwise, there are items → `complete`.
4. Otherwise → `zero`.

`stale` is never stored. It depends on who is reading and when, so `Evidence.state_at(now, max_age)` computes it on demand.

**Which error leads where:**

| Error kind | Raised when | State |
|---|---|---|
| `tool_not_allowed` | Tool not reviewed or not enabled | `denied` |
| `scope_violation` | Model asked for another namespace; server bound to another connection; or the result contained another namespace | `denied` |
| `auth` | Proxy answered 401/403, or the token could not be read | `denied` |
| `forbidden` | The upstream tool error says Kubernetes RBAC refused | `denied` |
| `invalid_arguments` | Arguments failed the tool's pydantic model | `missing` |
| `unavailable` | Could not connect | `missing` |
| `timeout` | Deadline passed | `missing` |
| `protocol` | The MCP exchange did not complete, or anything unclassified | `missing` |
| `schema_mismatch` | Server no longer advertises the reviewed schema | `missing` |
| `oversized` | Response exceeded the byte limit; all of it is discarded | `missing` |
| `invalid_output` | The result did not parse | `missing` |
| `upstream_error` | The tool reported an error that is not a denial | `missing` |
| `truncated` | More items than `max_items`; the first ones are kept | `partial` |

Real output from three calls made while writing this, against an unreachable endpoint:

```
call(pods_list, {})                         -> state missing, errors [unavailable]
call(pods_list, {"namespace":"kube-system"}) -> state denied,  errors [scope_violation]   (0.3 ms: no network request)
call("kubernetes__pods_delete", {})         -> state denied,  errors [tool_not_allowed]
```

Errors are a fixed list (`ErrorKind`) with fixed messages (`_MESSAGES`). Upstream error text and exception text never enter evidence, because both can contain resource names, URLs or tokens, and evidence goes to the model and later to the browser.

`build_evidence` is the only constructor either path should use. That is what makes an MCP answer and a direct read of the same pods comparable: [guide 3](direct-pod-view.md) shows the second path producing the same item IDs.

### 2.7 How the caller is authenticated on Kind (S1.3)

Some Kubernetes background first.

- A **ServiceAccount** is an identity for a program (as opposed to a person). Its full name looks like `system:serviceaccount:vyom:vyom-api`.
- A **ServiceAccount token** is a signed JWT issued by the Kubernetes API server. It states the identity (`sub`), an expiry (`exp`) and an **audience** (`aud`): who the token is meant to be shown to. A service should reject a token whose audience is not itself. That prevents a token meant for service A from being replayed against service B.
- **RBAC**: a `Role` lists allowed verbs on resources in one namespace; a `RoleBinding` gives a Role to an identity. `ClusterRole`/`ClusterRoleBinding` are the cluster-wide versions.
- **TokenReview**: an API call that asks the API server "is this token genuine, unexpired and valid for audience X, and whose is it?"
- **SubjectAccessReview**: an API call that asks "may identity I do verb V on resource R?" It evaluates RBAC without performing the action.

Now the two separate questions, answered by two separate things.

**"Who is calling the MCP endpoint?"** Answered by a sidecar, `kube-rbac-proxy`, a second container in the same pod as the MCP server.

```
backend                 proxy container (0.0.0.0:8443, TLS)        server container (127.0.0.1:8080)     Kubernetes API
   |  POST /mcp               |                                              |                              |
   |  Authorization: Bearer T |                                              |                              |
   |------------------------->|  TokenReview(T, audience vyom-mcp) ---------------------------------------->|
   |                          |<------------------ authenticated: system:serviceaccount:vyom:vyom-api ------|
   |                          |  SubjectAccessReview(vyom-api, create, vyom.dev/mcpendpoints/kubernetes) -->|
   |                          |<------------------ allowed ------------------------------------------------ |
   |                          |  forward ----------------------------------->|  list pods in demo  -------->|
   |                          |                                              |  (as kubernetes-mcp)         |
   |<------------------------ |<---------------------------------------------|<---- pod table --------------|
```

- The backend presents a token for `vyom-api`, issued for the audience `vyom-mcp`.
- The proxy does the TokenReview, then a SubjectAccessReview. The HTTP method becomes the verb (GET → `get`, POST → `create`, DELETE → `delete`).
- The resource in that check, `mcpendpoints` in API group `vyom.dev` with name `kubernetes`, **does not exist** as a real Kubernetes resource. It is only a name to hang a permission on. The Role `kubernetes-mcp-caller` grants it to `vyom-api`. Nothing in the Kubernetes API is opened by that grant.
- Only then does the proxy forward to the MCP server, which listens on `127.0.0.1` inside the pod. Containers in a pod share a network namespace, so the proxy can reach it and nothing outside the pod can.

**"As whom does the MCP server read Kubernetes?"** As its **own** ServiceAccount, `kubernetes-mcp`, whose only read permission is `list pods` in namespace `demo`. The caller's token is never passed on (the upstream default mode, "passthrough", would do exactly that, which is why `config.toml` changes it).

The useful consequence: the token the backend holds is useless against the Kubernetes API itself. It has the wrong audience, and `vyom-api` has no read permissions anyway. Stealing it lets you ask the MCP server for the pod list of `demo` and nothing else.

Results you can match to this (all in `mcp-check.sh`):

| Caller presents | Proxy answers | Why |
|---|---|---|
| Nothing | 401 | No token |
| A token for the normal Kubernetes audience | 401 | TokenReview fails on audience |
| Right audience, a ServiceAccount without the grant | 403 | SubjectAccessReview says no |
| The `vyom-api` token for `vyom-mcp` | 200 | Both pass |

In the host, a 401 or 403 seen by `_GuardedTransport` becomes error `auth` and state `denied`.

**TLS.** The proxy serves HTTPS with a self-signed certificate that `vyom-up.sh` (`mcp-up.sh` before S1.7) generates into `.local/mcp-tls/`. The host is told to trust exactly that certificate through `ca_file` in the server config. Without `ca_file` the connection fails verification, which is the correct default.

**Why a sidecar at all.** The upstream server has its own OAuth option, but in v0.0.67 it refuses to start with that option combined with "use my own identity for Kubernetes". That was found by running it, and is recorded as decision MCPK01.

**Known limits of this setup** (also in the handoff):

- To let the proxy check callers, the pod's ServiceAccount holds cluster-wide `create` on TokenReviews and SubjectAccessReviews. Those read no cluster resources, but they are cluster-scoped grants.
- `/healthz` goes through the proxy without authentication so the kubelet can probe it.
- On Kind the check scripts mint a 10-minute token with `kubectl create token`. The in-cluster way (a projected token volume mounted into the backend pod, refreshed automatically) arrives with S1.7 and is untested until then.

### 2.8 Say it back

Explain each of these out loud, as if to someone who has used LangChain but never heard of MCP. Then open the answer.

<details><summary>1. In one breath: what is MCP, and what does Vyom add on top of it?</summary>

MCP is a way to call tools that live in another program: you ask the server what tools it has and you ask it to run one. Vyom adds the rules MCP does not have: which tools may be used, with which arguments, in which namespace, and what part of the result is kept. Those rules live in the host.
</details>

<details><summary>2. The model asks for <code>namespace: kube-system</code>. Walk through what happens.</summary>

The model never sees a `namespace` argument, so it has to invent one. `_bind_arguments` finds a scope argument whose value differs from the trusted context and raises `scope_violation` before any network request. `build_evidence` turns that into evidence with state `denied`. Even if the host had a bug here, the server's ServiceAccount may only list pods in `demo`, so Kubernetes would refuse.
</details>

<details><summary>3. Why is "the namespace is empty" a different state from "I could not reach the cluster"?</summary>

Because a reader, human or model, draws opposite conclusions from them. An empty list read as complete means "nothing is unhealthy". A failed read means "I do not know". `zero` and `missing` keep those apart so that a failure can never be reported as good news.
</details>

<details><summary>4. Someone steals the token the backend sends to the MCP endpoint. What can they do with it?</summary>

Call the MCP endpoint, which will list pods in `demo` and nothing else. The token is issued for the audience `vyom-mcp`, so the Kubernetes API rejects it, and the identity it names (`vyom-api`) has no Kubernetes permissions anyway. The Kubernetes reads are done by the server's own identity.
</details>

<details><summary>5. The upstream server is upgraded and its tool gains a new argument. What happens on the next call, and why is that the right behaviour?</summary>

The advertised schema no longer hashes to the reviewed digest, so the call ends as `schema_mismatch` and nothing is called. A tool that changed is a tool nobody has reviewed; failing closed forces a person to look before the model can use it.
</details>

---

## Part 3 — Observability, from zero

### 3.1 Three signals, three questions

"Observability" means being able to answer questions about a running system from the outside, including questions you did not think of in advance. Three kinds of data are collected, because each is good at a different question and bad at the others.

| Signal | Question it answers | Shape | Cost per event | Stored in |
|---|---|---|---|---|
| **Metrics** | How many? How fast? How often does it fail? | Numbers over time | Near zero: a counter is incremented | Prometheus |
| **Logs** | What happened in this one event? | One JSON line per event | One line stored | Loki |
| **Traces** | Where did the time go inside one request? | A tree of timed steps | Several spans stored | Tempo |

- Metrics cannot tell you about one specific request. They are already aggregated.
- Logs can, but answering "what is the error rate?" from logs means scanning every line.
- Traces show the structure and timing of one request, but you first need to know which request to look at.

So you use them in that order: metrics to notice, logs to find an example, a trace to understand it (3.5).

The components on Kind, all pinned in `deploy/observability/charts.lock`:

| Component | Chart version | Job |
|---|---|---|
| Prometheus (via kube-prometheus-stack) | 92.3.0 | Scrapes and stores metrics |
| Grafana (same chart) | 92.3.0 | The viewer. Queries the three stores; stores no telemetry itself |
| Loki | 18.15.1 | Stores logs |
| Tempo | 3.1.0 | Stores traces |
| Alloy | 1.13.1 | The **collector**: one pod per node that reads log files and receives spans, then forwards them |

Everything keeps 48 hours of data and has explicit size and rate limits. All Services are ClusterIP; you reach Grafana through a localhost port-forward and a login.

### 3.2 Metrics

**The data model.** A **time series** is a metric name plus a set of label values, and its data is a list of (timestamp, number) samples. This is one series:

```
vyom_mcp_client_operations_total{operation="call",outcome="unavailable",server="kubernetes",tool="kubernetes__pods_list_in_namespace"}
```

Change any label value and it is a different series.

**How the numbers get to Prometheus.** The application keeps the current values in memory and serves them as plain text at `/metrics`. Prometheus **pulls** ("scrapes") that URL on an interval and stores what it sees with the scrape time. The app pushes nothing and does not know Prometheus exists. Real lines from this backend's `/metrics` after three failed MCP calls:

```
vyom_mcp_client_operations_total{operation="call",outcome="unavailable",server="kubernetes",tool="kubernetes__pods_list_in_namespace"} 1.0
vyom_mcp_client_operations_total{operation="call",outcome="scope_violation",server="kubernetes",tool="kubernetes__pods_list_in_namespace"} 1.0
vyom_mcp_client_operations_total{operation="call",outcome="tool_not_allowed",server="unlisted",tool="unlisted"} 1.0
vyom_mcp_client_operation_duration_seconds_bucket{le="0.5",operation="call",server="kubernetes",tool="kubernetes__pods_list_in_namespace"} 2.0
vyom_mcp_client_operation_duration_seconds_bucket{le="+Inf",operation="call",server="kubernetes",tool="kubernetes__pods_list_in_namespace"} 2.0
vyom_mcp_client_operation_duration_seconds_count{operation="call",server="kubernetes",tool="kubernetes__pods_list_in_namespace"} 2.0
vyom_mcp_client_operation_duration_seconds_sum{operation="call",server="kubernetes",tool="kubernetes__pods_list_in_namespace"} 0.05854887900932226
```

Look at the third line: the call named `kubernetes__pods_delete`, a tool that is not configured. It was recorded as `unlisted`, not under the name the caller supplied.

Prometheus also records a series called `up` for every target: 1 if the last scrape worked, 0 if not. That is the first thing to look at when a panel is empty.

**Metric types used here.**

- A **counter** only goes up (and resets to 0 on restart). Its absolute value is rarely interesting; you ask how fast it is growing with `rate(...)`. Names end in `_total`.
- A **histogram** records durations. It is really several counters: one per **bucket** (`_bucket{le="0.5"}` counts observations that took at most 0.5 s; buckets are cumulative), plus `_count` and `_sum`. From bucket growth Prometheus can estimate percentiles. The estimate is only as fine as the buckets, which is why the model histogram defines its own (0.25 s up to 120 s) rather than the defaults that stop at 10 s.
- A **gauge** goes up and down (queue length, memory). Vyom has one since S1.6: `vyom_collector_last_success_timestamp_seconds`, the time of the collector's last good run, so "how stale is this view" is `time() - that`.

**Cardinality: the one rule that shapes the code.** Every distinct combination of label values is a separate series that Prometheus keeps in memory and on disk. The number of series for a metric is the product of the distinct values of each label.

- `vyom_http_requests_total{method, route, status}`: 8 methods × a handful of route templates × a few dozen statuses. Bounded.
- The same metric labelled with the raw path: `/api/pods/web-769fb547f5-kxxc6`, `/no/such/path?x=1`, … one new series per distinct URL, forever. Anyone who can send requests can grow it without limit.

So every label in Vyom comes from a small fixed set:

| Label | Values come from | Bounding code |
|---|---|---|
| `method` | 7 known HTTP methods, else `OTHER` | `_METHODS` |
| `route` | The route **template** (`/api/health`), else `unmatched` | `_route_template` |
| `status` | HTTP status code | |
| `server`, `tool` | Configured IDs, else `unlisted` | `server_label`, `tool_label` in `McpHost.call` |
| `operation` | `call` or `discover` | |
| `outcome` | `ok` or an error kind (fixed enums) | `ErrorKind`, `ModelErrorKind` |
| `provider`, `model` | Operator configuration, pattern-checked | `ModelConfig` |
| `direction` | `input` or `output` | |

The same reasoning is why request IDs, pod names and trace IDs are never labels. Those belong in logs and traces.

**Every metric the backend defines** (`telemetry.py`):

| Metric | Type | Labels |
|---|---|---|
| `vyom_http_requests_total` | counter | method, route, status |
| `vyom_http_request_duration_seconds` | histogram | method, route |
| `vyom_mcp_client_operations_total` | counter | server, tool, operation, outcome |
| `vyom_mcp_client_operation_duration_seconds` | histogram | server, tool, operation |
| `vyom_model_requests_total` | counter | provider, model, outcome |
| `vyom_model_request_duration_seconds` | histogram | provider, model |
| `vyom_model_tokens_total` | counter | provider, model, direction |
| `vyom_model_usage_unavailable_total` | counter | provider, model |
| `vyom_chat_requests_total` (S1.5) | counter | outcome |
| `vyom_chat_duration_seconds` (S1.5) | histogram | none |
| `vyom_graph_step_duration_seconds` (S1.5) | histogram | step |
| `vyom_collector_runs_total` (S1.6) | counter | collector, outcome |
| `vyom_collector_duration_seconds` (S1.6) | histogram | collector |
| `vyom_collector_last_success_timestamp_seconds` (S1.6) | gauge | collector |

`vyom_model_usage_unavailable_total` exists because of the rule "unavailable is not zero". If a provider answers without a usage report, adding 0 to the token counter would make the token total look complete when it is not. Instead nothing is added to tokens and this counter goes up, so a dashboard can show "token count is missing N replies".

**PromQL, the query language.** Four patterns cover most needs:

```
# Requests per second, by route
sum by (route) (rate(vyom_http_requests_total[5m]))

# MCP failures per second, by outcome
sum by (outcome) (rate(vyom_mcp_client_operations_total{outcome!="ok"}[5m]))

# Share of model requests that failed
sum(rate(vyom_model_requests_total{outcome!="ok"}[5m])) / sum(rate(vyom_model_requests_total[5m]))

# 95th percentile MCP call duration
histogram_quantile(0.95, sum by (le) (rate(vyom_mcp_client_operation_duration_seconds_bucket[5m])))
```

Read `rate(x[5m])` as "per-second growth of x, averaged over the last 5 minutes". `sum by (label)` then adds series together, keeping only that label.

**How Prometheus finds targets in the cluster.** kube-prometheus-stack includes an operator that reads `ServiceMonitor` objects ("scrape the Services with these labels on this port"). The backend will get one when it is deployed in S1.7. Until then, `curl http://127.0.0.1:8000/metrics` is the only way to see backend metrics.

### 3.3 Logs

**Structured logging.** Instead of a sentence with values pasted in (`"call to pods_list failed after 58ms"`), Vyom logs one JSON object per event: a constant message plus named fields. Real lines:

```json
{"ts": "2026-10-12T08:57:17.890+00:00", "level": "warning", "service": "vyom-api", "logger": "vyom.mcp", "message": "mcp operation finished", "outcome": "unavailable", "mcp_server": "kubernetes", "mcp_tool": "kubernetes__pods_list_in_namespace", "duration_ms": 58.3, "operation": "mcp.call", "error_type": "ConnectError"}
{"ts": "2026-10-12T08:57:17.892+00:00", "level": "warning", "service": "vyom-api", "logger": "vyom.mcp", "message": "mcp operation finished", "outcome": "tool_not_allowed", "mcp_server": "unlisted", "mcp_tool": "unlisted", "duration_ms": 0.2, "operation": "mcp.call", "error_type": "_Failure"}
```

Why constant messages: you can filter and count on fields without regular expressions, and there is no place for a payload to slip into the sentence.

Notice `error_type` is a class name (`ConnectError`), never the exception's message. The message of a connection error typically contains the URL.

These two lines have no `trace_id` because they came from a standalone script with no surrounding request. Inside a real HTTP request the formatter adds `trace_id` and `span_id` from whatever span is current. One detail worth knowing when you read the code: `McpHost.call` writes its log line *after* its own span has closed, so the line carries the IDs of the enclosing request span; `ModelClient.chat` writes its line *inside* its span.

**How a log call works in the code.**

```python
_mcp_log.log(level, "mcp operation finished", extra={"operation": "mcp.call", "outcome": outcome, ...})
```

- Python's `logging` copies everything in `extra` onto the record.
- `JsonFormatter.format` then builds the JSON: fixed keys, trace IDs if a span is current, and from the record **only the names in `LOG_FIELDS`**. A field not in that set is silently dropped. So adding `extra={"prompt": text}` somewhere by mistake logs nothing.
- If the record has exception info, only the class name is added.
- Level is `info` for `ok`, `warning` otherwise.

`configure_logging` also does three defensive things: it filters out records from client libraries (`mcp`, `httpx`, `openai`, `langchain*`, `langsmith`), which log URLs and bodies as free text; it disables uvicorn's access log, which prints raw request lines with query strings; and the request middleware skips `/api/health` and `/metrics` so probes and scrapes do not flood the log.

**How logs reach Loki.** The application only writes to stdout.

```
app stdout
  -> container runtime writes /var/log/pods/<ns>_<pod>_<uid>/<container>/0.log on the node   (CRI format: time, stream, line)
  -> Alloy (DaemonSet: one pod per node, /var/log mounted read-only)
       discovery.kubernetes   find pods on THIS node, only in namespaces vyom and observability
       discovery.relabel      attach labels: namespace, service_name, container
       stage.cri              strip the runtime's prefix, recover the original line
       stage.replace          redact anything that looks like  token=..., authorization: ..., api_key=...
       stage.structured_metadata   move the pod name out of the index
  -> Loki
```

The namespace list is a deliberate boundary: workloads in `demo` (or any future tenant namespace) are not collected. The MCP pod is in `vyom`, so its logs are collected; they were inspected for content before that was accepted (decision MCPK05).

**How Loki stores them.** Loki does **not** index log text. It indexes a few **labels** and stores the lines compressed, grouped into **streams** (one stream per distinct label set). A query first selects streams by label, then scans their lines.

- Labels here: `namespace`, `service_name` (from the pod label `app.kubernetes.io/name`), `container`, `stream` (stdout/stderr).
- The cardinality rule applies again: each label combination is a stream. The pod name changes on every restart, so it is kept as **structured metadata** (attached to each line, queryable, not indexed) rather than as a label. Trace IDs live inside the JSON line.

**LogQL.** A stream selector in braces, then a pipeline:

```
{namespace="vyom"}                                             # everything collected from the vyom namespace
{namespace="vyom", service_name="kubernetes-mcp"}              # the MCP pod (works today)
{service_name="vyom-api"} | json | outcome != "ok"             # backend failures (from S1.7)
{service_name="vyom-api"} | json | trace_id = "4bf92f35..."    # every line of one request
sum by (outcome) (count_over_time({service_name="vyom-api"} | json [5m]))   # logs turned into a metric
```

`| json` parses each line so its fields can be filtered.

### 3.4 Traces

**Anatomy of a span.** One timed step:

| Part | Example |
|---|---|
| name | `mcp.client.call` |
| trace ID | 32 hex characters, shared by every span of the request |
| span ID / parent span ID | 16 hex characters each; the parent link builds the tree |
| kind | `CLIENT` (an outgoing call), `SERVER` (handling an incoming one), `INTERNAL` |
| start and end time | |
| attributes | `vyom.mcp.server=kubernetes`, `vyom.outcome=forbidden`, `vyom.evidence.state=denied` |
| events | timestamped notes inside the span, e.g. a recorded exception |
| status | unset, or `ERROR` |

A **trace** is all spans with one trace ID. Tempo stores spans; Grafana draws them as a waterfall.

**How nesting happens in the code.** OpenTelemetry keeps "the current span" in a Python context variable. `start_as_current_span` reads it (that becomes the parent), sets itself as current, and restores the previous one on exit. Context variables follow `await`, so this works across async code without passing anything by hand.

```python
with telemetry.tracer().start_as_current_span("mcp.client.call", ...) as span:      # parent: the request span, if any
    ...
    with telemetry.tracer().start_as_current_span("evidence.normalize") as normalize:  # parent: mcp.client.call
        ...
```

**Propagation between services.** For two services to share a trace, the caller sends its trace ID and current span ID in an HTTP header, W3C `traceparent`:

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             version - trace ID (32 hex)        - parent span ID  - flags (01 = sampled)
```

The receiver starts its spans under that parent. In Vyom today this matters in one direction only: FastAPI's instrumentation reads an incoming `traceparent`. The trace ends at Vyom's own client spans; the upstream MCP server's tracing is not enabled and the model provider is external. The project's wording for this is an "owned-component trace".

**Sampling.** Many systems keep only a fraction of traces. Vyom keeps all of them for now (S1 demo traffic is small).

**From span to Tempo.**

```
span ends
  -> BatchSpanProcessor     in-memory queue, max 512 spans; exports up to 128 every 2 s on a background thread
  -> ScrubbingExporter      removes URL queries, header attributes, exception text
  -> OTLPSpanExporter       HTTP POST to OTEL_EXPORTER_OTLP_ENDPOINT (3 s timeout)
  -> Alloy  otelcol.receiver.otlp      ports 4317 (gRPC) and 4318 (HTTP)
            memory_limiter             refuses data above 96 MiB
            attributes "scrub"         deletes header attributes, url.query, gen_ai/llm prompt and completion attributes
            batch                      2 s / 256 spans
            exporter                   to Tempo; queue of 200 batches, retries for up to 1 minute
  -> Tempo
```

**OTLP** is the OpenTelemetry wire format; it is how the spans travel on both hops. The request thread only appends a finished span to a queue. If the queue is full, or Alloy or Tempo is down, spans are dropped and the request is unaffected.

If neither `OTEL_EXPORTER_OTLP_ENDPOINT` nor `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set, no exporter is attached at all. Spans are still created (so logs still get trace IDs) and then discarded. That is the situation when you run the backend locally.

**Resource attributes** describe the process, not the step: `service.name=vyom-api`, `service.version`. Tempo and Grafana use `service.name` to group spans.

What a chat request looks like (the graph spans were added in S1.5; the rest are from this guide):

```
POST /api/chat                      (FastAPI instrumentation, kind SERVER)
  chat.graph                        outcome, number of tool calls
    graph.propose
      model.client.chat             provider, model, outcome, tool_calls, input/output tokens
    graph.collect
      mcp.client.call               server, tool, outcome, evidence.state
        evidence.normalize          evidence.state, evidence.items
    graph.answer
      model.client.chat             (answer from the evidence)
```

The MCP SDK adds a few client spans of its own under `mcp.client.call`. Your live run of `chat-check.sh` found 12 spans in this one trace.

Notice what the attributes are: IDs from configuration, counts and fixed outcome names. No argument, result, prompt or answer.

**TraceQL**, Tempo's query language, selects spans by attribute:

```
{ resource.service.name = "vyom-api" && span.vyom.outcome != "ok" }
{ name = "model.client.chat" && duration > 5s }
```

### 3.5 Correlation: why all three together

The link between the signals is the trace ID, written into every log line by `JsonFormatter`. A debugging session then goes:

1. **Metric**: the dashboard panel for `vyom_mcp_client_operations_total` shows `outcome="forbidden"` rising since 14:05.
2. **Logs**: in Explore, `{service_name="vyom-api"} | json | outcome = "forbidden"`. Each line has a `trace_id`.
3. **Trace**: Grafana shows an "Open trace" link next to that field. The trace shows the request, the model call that proposed the tool, the MCP call that was refused, and how long each took.
4. **Back to logs**: from a span, "Logs for this span" runs a Loki query for that trace ID in a ±5 minute window, showing every line the request wrote.

Both jumps are configuration, in `deploy/observability/kube-prometheus-stack.values.yaml` under the Grafana data sources:

- on the Loki data source, a **derived field** with the regex `"trace_id":\s*"([0-9a-f]{32})"` pointing at Tempo;
- on the Tempo data source, **traces to logs** with the query `{service_name="..."} | json | trace_id="..."`.

So the formatter's exact output (`"trace_id": "<32 hex>"`) is a small contract with Grafana. Change the key name and the link disappears.

Two dashboards are provisioned as code from `deploy/observability/dashboards/`: `vyom-cluster.json` and `vyom-agent.json`. MCP and model panels are not on them yet.

### 3.6 Vyom's extra rule: telemetry carries no payloads

Telemetry is copied into three databases, kept for days, and read by whoever operates them, with coarser access control than the application has. So prompts, answers, tool arguments, tool results, headers, URLs with queries and exception messages must never go in. The code enforces this in layers, so one mistake does not leak:

| # | Layer | Stops | Where |
|---|---|---|---|
| 1 | **Telemetry functions take no payload** | `record_mcp_operation` and `record_model_request` have no parameter for arguments, results or messages | `telemetry.py` |
| 2 | **Log field allowlist** | A stray `extra=` field; exception messages and tracebacks | `LOG_FIELDS`, `JsonFormatter` |
| 3 | **Library loggers dropped** | URLs and bodies logged as free text by `mcp`, `httpx`, `openai`, LangChain, LangSmith | `_SILENCED_LOGGERS` |
| 4 | **Fixed error kinds** | Provider and upstream error text reaching logs, spans, evidence or the caller | `ErrorKind`, `ModelErrorKind`, both `_classify` functions |
| 5 | **Span scrubber** | URL queries, header attributes and exception text added by automatic instrumentation | `ScrubbingExporter` |
| 6 | **Alloy** | The same again on the way through, plus `gen_ai.*`/`llm.*` prompt attributes and token-like text in log lines | `config.alloy` |
| 7 | **LangSmith forced off** | LangChain exporting whole prompts to a third party if `LANGSMITH_*` happens to be set | `tracing_context(enabled=False)` in `model.py` |

Layer 7 deserves a sentence since you know LangChain: LangSmith tracing is switched on by environment variables alone, and it uploads message content. An operator who sets those variables for another project would silently start exporting Vyom's prompts. The adapter disables it per request regardless of environment.

How this is proven, not just intended: the tests and live checks plant **markers** (a unique string in the prompt, a literal env value on the demo pod, a known pod name, the key itself) and then search every span, log line, metric and error text for them. Your `model-check.sh` run reported exactly that: nothing found in 15 spans and 12 log lines.

And telemetry must never block a request: metrics are in-memory increments, logs are a write to stdout, and span export is asynchronous with a bounded queue. If Tempo, Loki or Alloy is down, data is dropped and counted, and the request still succeeds.

### 3.7 Say it back

<details><summary>1. You have one number, one line and one tree. Which signal is which, and which do you open first when "chat feels slow"?</summary>

Metrics are numbers over time, logs are one line per event, traces are a tree of timed steps for one request. Start with metrics to see whether it is slow for everything or one step (`vyom_graph_step_duration_seconds` by step), find one slow request's log line, then open its trace to see where the time went.
</details>

<details><summary>2. Why is a pod name never a metric label, when it is fine in evidence and in the UI?</summary>

Every distinct label value creates a new time series that Prometheus keeps. Pod names change on every rollout, so the number of series would grow without limit. It is also a payload: telemetry stores are read with coarser access control than the application. Evidence goes to the person who asked; metrics go to whoever operates Prometheus.
</details>

<details><summary>3. A developer adds <code>extra={"question": text}</code> to a log call. What ends up in Loki?</summary>

Nothing from that field. `JsonFormatter` copies only the names in `LOG_FIELDS`, and `question` is not one of them. The mistake is harmless by construction, which is the point of an allowlist over a blocklist.
</details>

<details><summary>4. Tempo is down for ten minutes. What does a user asking a question notice?</summary>

Nothing. Finished spans go into a bounded in-memory queue and are exported on a background thread; when the queue is full they are dropped. The request never waits for the export. What is lost is the traces for those ten minutes.
</details>

<details><summary>5. How does clicking a log line in Grafana open the right trace?</summary>

Every log line written inside a request carries `"trace_id": "<32 hex>"`. The Loki data source has a derived field with a regular expression for exactly that text, linked to Tempo. The formatter's output format is a small contract with that configuration.
</details>

---

## Part 4 — Reading the code

All backend paths are under `backend/src/vyom/`. Suggested order: small data types first, then the two workflows, then telemetry, then deployment.

### 4.1 Reading order

| # | File | Read for | Size |
|---|---|---|---|
| 1 | `context.py` | `TrustedContext`: workspace, connection, cluster UID, namespace. The server-side "where am I allowed to look" | tiny |
| 2 | `evidence.py` | `State`, `ErrorKind`, `Evidence`, and `build_evidence` (the only constructor) | medium |
| 3 | `credentials.py` | `file:/path` or `env:NAME` references; config never holds a secret | tiny |
| 4 | `mcp_client/registry.py` | `OperatorConfig`, `ServerConfig`, `Limits`: what the operator may configure | small |
| 5 | `mcp_client/tools.py` | `ToolSpec`: Vyom's own definition of a tool | small |
| 6 | `mcp_client/kubernetes.py` | The one real tool: argument model, table parser, schema digest | small |
| 7 | `mcp_client/host.py` | `McpHost.tools`, `discover`, `call`. The core of S1.2 | large |
| 8 | `agent/model.py` | `ModelClient.chat` around `ChatOpenAI` | medium |
| 9 | `telemetry.py` | Logs, metrics, traces and the scrubbing rules | medium |
| 10 | `api/app.py` | `create_app`: health, plus the routes of guides 2 and 3, and `telemetry.instrument(app)` | small |

Notes on the small files before the walkthroughs:

- **`context.py`**. `TrustedContext` is frozen (cannot be modified after creation) and pattern-checked. Today one context is configured by the operator and used for every request (`FixedContextResolver`). In S6 a different resolver will derive it from a verified login. The rest of the code only ever asks a resolver, so that swap touches one place.
- **`credentials.py`**. Configuration holds a *reference* (`file:/run/secrets/token`, `env:OPENROUTER_API_KEY`), never a value. `read_credential` resolves it each time it is needed, so rotation needs no restart. Two careful details: `check_reference` does not echo a bad input in its error (someone might paste the key itself into the field), and `CredentialUnavailable` carries no path.
- **`registry.py`**. Everything is `frozen` and `extra="forbid"` (an unknown key in the config file is an error, not ignored). URLs may not contain credentials or a query. `http://` needs an explicit `allow_cleartext`. `Limits` have upper bounds, so a config typo cannot set a 10-hour timeout. `hide_input_in_errors` keeps pydantic from printing the offending value.
- **`tools.py`**. `ToolArguments` is the base for argument models: `strict=True` (no silent type coercion: `"5"` is not accepted for an int) and `extra="forbid"` (an unexpected argument is an error). `ToolSpec` is what a reviewer fills in for each tool.
- **`kubernetes.py`**. `project_pod_table` finds column positions from the header line, then slices each row at those positions. It requires six named columns and that every row is a `Pod`; anything else raises, which the host turns into `invalid_output`. Parsing by header position rather than by splitting on spaces is what lets `4 (2m ago)` and `<none>` survive.

### 4.2 Workflow A: one MCP tool call, step by step

Start at `McpHost.call(tool, arguments, context)` in `mcp_client/host.py`. `tool` and `arguments` are untrusted (the model proposed them). `context` is trusted.

1. **Is the tool known?** `self._specs.get(tool)`. `_specs` was filled in `__init__` with only the specs that are both in code and enabled by the operator. Unknown → `TOOL_NOT_ALLOWED`. The telemetry labels become `unlisted`, decided here before anything is recorded.
2. **Right connection?** The server's `connection_id` must equal the context's. Otherwise `SCOPE_VIOLATION`. This is what will stop workspace A's request from using workspace B's endpoint once there is more than one.
3. **Arguments.** `_bind_arguments`:
   - If the model supplied a scope argument (`namespace`) with a value other than the trusted one → `SCOPE_VIOLATION`, and no network request is made. Repeating the trusted value is accepted and removed.
   - The rest is validated by the tool's pydantic model (`PodsListArguments`) → `INVALID_ARGUMENTS` on failure. This is where `app=web*` was refused in your live run: `*` is outside the selector pattern.
   - The trusted namespace is then added by the host. The dictionary sent upstream is `{validated arguments} + {scope from context}`, in that order, so scope always wins.
4. **Session.** `_session`:
   - reads the bearer token from its reference (`server.read_credential()`);
   - wraps the HTTP transport in `_GuardedTransport`. An httpx *transport* is the lowest layer, the thing that actually sends a request and returns a response, so wrapping it sees every exchange regardless of what the SDK does above. It counts response bytes (stops at `max_response_bytes`) and notes a 401/403 in a small `_Wire` object, because the SDK does not report either fact in a usable way;
   - puts one deadline around everything with `anyio.fail_after(connect + call timeout)`. Individual httpx timeouts apply per network operation; this outer one caps the total, so a server that answers slowly but steadily still ends on time;
   - `trust_env=False`, so proxy or CA settings in the environment cannot redirect the connection;
   - connects with the SDK client (`client_for`), which performs **initialize**.
5. **Call.** `_invoke`:
   - lists the server's tools again on this session and compares the schema digest (`_mismatch`) → `SCHEMA_MISMATCH` if the server changed;
   - `client.call_tool(...)`;
   - joins the text blocks of the result;
   - if the server flags an error, `spec.error_kind` reads the text only to tell "forbidden" from other errors, then discards it;
   - `spec.project(...)` parses the result. Any exception in the projector → `INVALID_OUTPUT`.
6. **Anything that went wrong** lands in `except Exception` and goes through `_classify`. Async libraries that run tasks concurrently raise **exception groups** (one exception wrapping several); `_leaves` flattens them. Then, in priority order: oversized seen on the wire → `OVERSIZED`; 401/403 seen → `AUTH`; one of the host's own `_Failure`s → its kind; a timeout → `TIMEOUT`; a transport error → `UNAVAILABLE`; anything else → `PROTOCOL`. Only exception *types* are examined. The returned class name becomes `error_type` in the log.
7. **Normalize.** `build_evidence` in `evidence.py`:
   - drops everything and reports `SCOPE_VIOLATION` if any item is from another namespace (a second check on the result, independent of the check on the arguments);
   - truncates at `max_items`;
   - assigns each item its ID;
   - computes `state` (2.6).
8. **Record.** The span `mcp.client.call` (with child `evidence.normalize`) ends, then `telemetry.record_mcp_operation` writes the counter, histogram and log line.

`call` never raises for expected failures: it always returns `Evidence`, with errors inside. That keeps the chat graph simple: its tool step always gets evidence back, and only has to look at the state ([guide 2](chat-graph.md)).

Two neighbours to read right after:

- `McpHost.tools()`: what the model will be shown. Note the loop that removes scope arguments from the schema.
- `McpHost.discover(server_id)`: connect, list, and report per enabled tool whether it is callable. It reports how many other tools the server advertises (`not_enabled`) but never enables them. Useful for a status page; not on the path of a tool call.

Also note `transport_factory` in the constructor. It exists so tests can substitute an in-memory transport connected to a fixture server; production uses `_network_transport`.

Tests that show each rule being enforced: `backend/tests/test_mcp_host.py` (against `tests/mcp_fixture.py`, a throwaway MCP server used only in tests), `test_kubernetes_tools.py` (the table parser against a captured real table in `tests/data/`), `test_evidence.py`. The test names read as the list of rules, for example `test_proposed_scope_endpoint_and_credential_arguments_never_reach_upstream` and `test_oversized_output_is_discarded_not_truncated_into_evidence`.

### 4.3 Workflow B: one model request

Start at `ModelClient.chat(messages, tools)` in `agent/model.py`. You will recognise most of it; the interesting parts are what was added around `ChatOpenAI`.

1. Start span `model.client.chat` with the configured provider and model.
2. `_invoke`:
   - read the key from its reference (`MISSING_CREDENTIAL` if absent, before any request);
   - build an `httpx.AsyncClient` over `_CappedTransport` (the same byte-limit idea as the MCP host) with `trust_env=False`;
   - build `ChatOpenAI(..., max_retries=0)`. The default is to retry; here a failure is reported once, and any retry policy will be an explicit decision in the graph rather than hidden in the client;
   - `bind_tools` with the host's descriptors converted by `_wire_tool` to the OpenAI function format (the JSON in 2.5);
   - `ainvoke` inside `tracing_context(enabled=False)`;
   - any exception → `_classify` → a `ModelError` with a fixed kind. `raise ... from None` cuts the chain so the original exception, with the provider's text, is not attached.
3. `_usage(message)`: token counts from the provider's own report in `response_metadata["token_usage"]`. Deliberately not `usage_metadata`, because LangChain fills a missing report with zeros and the project rule is "unavailable is not zero". Usage is read before the well-formedness check, so tokens you paid for are counted even if the reply is then rejected.
4. `_well_formed(message)`: rejects a reply with `invalid_tool_calls` (LangChain's holding place for calls whose arguments were not valid JSON), or a call without an ID or a name → `MALFORMED_TOOL_CALL`.
5. Return `Reply(message, finish, usage)`. `message` is the ordinary LangChain `AIMessage`, so the chat graph appends it to its message list directly. `finish` is `tool_calls`, `stop`, `length` (cut off at `max_output_tokens`) or `other`.
6. `finally`: set span attributes and call `telemetry.record_model_request`.

How `_classify` maps failures, by class and status code only:

| What happened | Kind |
|---|---|
| The byte cap tripped | `oversized` |
| `openai.APITimeoutError`, HTTP 408/504 | `timeout` |
| HTTP 401/403 | `auth` |
| HTTP 402 | `quota` |
| HTTP 429 | `rate_limited` |
| HTTP 5xx, connection error | `unavailable` |
| Other 4xx (e.g. unknown model) | `rejected` |
| LangChain could not build the message because of its tool-call fields | `malformed_tool_call` |
| An error object inside a 200 response (some gateways do this) | by its integer code, else `unavailable` |
| Anything else | `invalid_response` |

Division of labour to notice: the adapter only checks that a tool call is *well formed*. Whether the tool is *allowed* and its arguments *valid* is decided by `McpHost.call` in Workflow A. One place owns tool policy.

Tests: `backend/tests/test_model.py`, using scripted HTTP responses through the `transport` constructor argument. Live: `scripts/model_live_check.py`.

### 4.4 Workflow C: how a line of telemetry is produced and travels

In `telemetry.py`, top to bottom:

- `LOG_FIELDS`, `_SILENCED_LOGGERS`, `JsonFormatter`: read `format` to see the allowlist and how `trace_id`/`span_id` are taken from the current span.
- `configure_logging`: one stdout handler on the root logger, the library filter, uvicorn's access log disabled.
- `_observe_request`: FastAPI middleware wrapping every request. The `finally` block guarantees a count even when the handler raises (status stays 500). Note `_route_template` (the label is `/api/health` or `unmatched`, never the raw path).
- `record_mcp_operation`, `record_model_request`: the only two places MCP and model telemetry are written. Callers pass already-bounded labels. `record_chat`, `record_graph_step` (S1.5) and `record_collector_run` (S1.6) follow the same pattern.
- `ScrubbingExporter`: wraps the OTLP exporter. A finished span is read-only, so `_scrub` builds a new one with cleaned attributes (`_scrub_attributes`) and events (`_scrub_event`, which keeps only `exception.type`).
- `tracer_provider`: created once per process; attaches the exporter only if an OTLP endpoint variable is set; note the bounded queue.
- `instrument(app)`: attaches the middleware, `/metrics`, and FastAPI's automatic request spans (one server span per request; health and metrics excluded).

The journey after the process:

| Signal | Leaves the backend as | Picked up by | Stored in |
|---|---|---|---|
| Logs | JSON lines on stdout | Alloy reads node log files | Loki |
| Traces | OTLP over HTTP to Alloy (4318) | Alloy limits, scrubs, batches, forwards | Tempo |
| Metrics | Text at `/metrics` | Prometheus scrapes (not until S1.7) | Prometheus |

Tests: `backend/tests/test_telemetry.py`.

### 4.5 Deployment files (Kind)

| Path | What it is |
|---|---|
| `deploy/kind/cluster.yaml` | The Kind cluster `vyom` |
| `deploy/kind/demo.yaml` | Namespace `demo`: one healthy pod (`web`, with a marker env value used to prove nothing leaks) and one failing pod (`broken`, ImagePullBackOff) |
| `deploy/observability/charts.lock` | The four pinned Helm charts with archive checksums, so an install cannot silently pick up a different chart |
| `deploy/observability/*.values.yaml` | Settings per chart: retention, limits, what is switched off |
| `deploy/observability/config.alloy` | The collector pipeline. Worth reading once against the two diagrams in 3.3 and 3.4 |
| `deploy/observability/dashboards/*.json` | Two Grafana dashboards, provisioned as code |
| `deploy/chart/vyom/files/kubernetes-mcp.toml` (was `deploy/kubernetes-mcp/config.toml`) | The MCP server's settings: read-only, one enabled tool, Secrets denied, bound to localhost, log level 0 (higher levels log parameters and results) |
| `deploy/chart/vyom/templates/kubernetes-mcp.yaml` and `identities.yaml` (were `deploy/kubernetes-mcp/manifests.yaml`) | Read in this order, matching 2.7: the two ServiceAccounts; the Role in `demo` (pods `list` only); the ClusterRole letting the proxy create TokenReviews and SubjectAccessReviews; the Role granting `vyom-api` the made-up endpoint resource; the proxy's ConfigMap naming that resource; the Service (ClusterIP, 8443); the Deployment with its two containers (`server`, `proxy`) |

Both images in the Deployment are pinned by digest (`@sha256:…`), not by tag, so the image cannot change underneath a tag.

### 4.6 Scripts

| Script | Does |
|---|---|
| `scripts/observability-up.sh` / `observability-check.sh` | Install the stack; verify it through localhost port-forwards |
| `scripts/vyom-up.sh` (was `mcp-up.sh`) | Generate the endpoint certificate once into `.local/mcp-tls/`, build and load the images, install the chart and the demo workloads |
| `scripts/mcp-check.sh` + `mcp_live_check.py` | 22 live checks: RBAC, who is refused, pod list equals `kubectl`, nothing sensitive in telemetry |
| `scripts/model-check.sh` + `model_live_check.py` | The live model checks you ran |
| `scripts/dev-up.sh` | Run the backend on your machine against Kind (guides 2 and 3) |
| `scripts/chat-check.sh`, `scripts/pods-check.sh` | The live gates for the chat and the pod view |
| `scripts/check-docs.py` | Consistency of the docs and tracker |

The `*_live_check.py` files are also the shortest complete examples of how to build an `OperatorConfig`, an `McpHost` and a `ModelClient` and call them. `model_live_check.py` does by hand what the chat graph now does: propose, validate with the host, feed a result back, answer.

### 4.7 Frontend

See [guide 4](frontend-console.md).

---

## Part 5 — See it happen

Each of these is local. Run from the repository root unless noted.

**Metrics and logs from the bare backend**

```sh
cd backend && uv run uvicorn vyom.api.app:app --host 127.0.0.1 --port 8000
# second terminal:
curl -s 'http://127.0.0.1:8000/no/such/path?secret=1'
curl -s http://127.0.0.1:8000/metrics | grep vyom_http
```

Look for: the request counted under `route="unmatched"` (not the raw path), and in the first terminal a JSON log line with no query string in it. `/api/health` is counted in metrics but deliberately not logged.

**The host's rules, one test at a time**

```sh
cd backend
uv run pytest -q tests/test_mcp_host.py -v      # read the test names: each is one rule
uv run pytest -q tests/test_model.py -v
```

A good exercise: in `host.py`, comment out the scope check inside `_bind_arguments`, run the tests, see which one fails, then restore it.

**The real MCP path on Kind**

```sh
./scripts/mcp-check.sh
kubectl --context kind-vyom -n demo get pods
kubectl --context kind-vyom -n vyom logs deployment/kubernetes-mcp --all-containers --since=10m
```

Compare the PASS lines with sections 2.5 and 2.7. The last command shows what the server and proxy log: sessions and refusals, no arguments or pod names.

**RBAC, asked directly**

```sh
kubectl --context kind-vyom auth can-i list pods -n demo        --as=system:serviceaccount:vyom:kubernetes-mcp   # yes
kubectl --context kind-vyom auth can-i list pods -n kube-system --as=system:serviceaccount:vyom:kubernetes-mcp   # no
kubectl --context kind-vyom auth can-i list pods -n demo        --as=system:serviceaccount:vyom:vyom-api         # no
```

`auth can-i --as` is a SubjectAccessReview made from the command line: the same question the proxy asks.

**Grafana**

```sh
kubectl --context kind-vyom -n observability port-forward svc/grafana 3000:80 --address 127.0.0.1
# http://127.0.0.1:3000  user admin, password in .local/grafana-admin-password
```

In Explore, pick Loki and run `{namespace="vyom"}` to see the MCP pod's collected logs. Pick Prometheus and run `up` to see what is being scraped. Backend metrics and chat traces are not there yet: the backend runs on your machine, outside the cluster, until S1.7.

---

## Part 6 — Terms in one place

| Term | Meaning here |
|---|---|
| Host / client / server | Vyom's `McpHost` / the SDK connection / the upstream Kubernetes MCP server |
| JSON-RPC | The message format MCP uses: requests with an `id`, responses, notifications |
| Streamable HTTP | The MCP transport over one HTTP endpoint, with JSON or event-stream responses |
| Capabilities | What each side declares it supports during `initialize`; Vyom requires `tools` |
| Tool ID | `<server>__<tool>`, e.g. `kubernetes__pods_list_in_namespace`; safe as a model-facing function name |
| ToolSpec | Vyom's reviewed definition of an upstream tool |
| Schema digest | SHA-256 of the server's advertised input schema; a change disables the tool until reviewed |
| Projection | Reducing an upstream result to the few fields Vyom keeps |
| Trusted context | Server-side scope (workspace, connection, cluster, namespace); never from the browser or the model |
| Scope argument | A tool argument (here `namespace`) that the host fills in and the model never sees |
| Evidence | The normalized result of one collection: source, time, state, coverage, items, errors |
| Operator config | One JSON file: context, MCP servers, model, Kubernetes API. The API loads the file named by `VYOM_CONFIG` at start |
| Credential reference | `file:/path` or `env:NAME`; the secret itself is read at call time |
| ServiceAccount | A Kubernetes identity for a program |
| Audience | Who a token is meant for; `vyom-mcp` for the MCP endpoint |
| TokenReview / SubjectAccessReview | Kubernetes API calls the proxy uses to check a token and a permission |
| Sidecar | A helper container in the same pod; here the authenticating proxy |
| Time series | One metric name plus one set of label values, with samples over time |
| Cardinality | Number of distinct label combinations; kept small on purpose |
| Scrape | Prometheus fetching `/metrics` from a target |
| Counter / histogram / gauge | A number that only rises / bucketed counts of durations / a number that goes up and down |
| Stream (Loki) | All log lines sharing one label set |
| Structured metadata | Per-line fields in Loki that are queryable but not indexed (the pod name) |
| Span / trace | One timed step / all steps of one request, linked by a trace ID |
| Propagation | Carrying the trace ID to another service in the `traceparent` header |
| OTLP | The OpenTelemetry wire format for spans |
| Alloy | The collector on each node: reads logs, receives spans, forwards both |
| Derived field | Grafana's rule that turns a `trace_id` in a log line into a link to Tempo |
