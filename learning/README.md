# Learning material

Study notes and exercises for understanding Vyom. None of this is project documentation, none of it is used at runtime, and it gives no credit toward any task. The authoritative documents are in [docs/](../docs/TRACKER.md).

## The Vyom guides (S1.1–S1.6)

Four guides, written to be read in order. Each starts with the idea in plain words and an analogy, then says where the simple picture stops being true, then walks the code, and ends with questions to answer out loud ("Say it back"). If you cannot explain an answer in your own words without looking, reread that section. The guides get harder as they go; the first sections of each are the easy ones.

| # | Guide | Covers | You will be able to explain |
|---|---|---|---|
| 1 | [MCP and observability: the foundations](mcp+observability-bootstrap.md) | S1.1–S1.4, S1.9 | What MCP is and why Vyom does not trust it; what evidence is and its six states; how the MCP endpoint authenticates callers; metrics, logs and traces and why they carry no payloads |
| 2 | [The chat](chat-graph.md) | S1.5 | How a question becomes a cited answer in three steps; every way a question can end; what stops the model going beyond the evidence, and what does not |
| 3 | [The direct pod view](direct-pod-view.md) | S1.6 | Why there are two paths; why the collector asks Kubernetes for a table; the three identities; how the two paths were shown to agree |
| 4 | [The console](frontend-console.md) | The UI for all of the above | What runs in the browser and what does not; how a value gets from the API to the screen; how the design tokens work; why "configured" is not drawn as "healthy" |

About an hour each if you read with the code open and do the exercises.

**The one-paragraph version of everything.** You ask a question in the browser. The backend lets a model propose one read, makes that read itself through a locked-down MCP server, shows the result to the model, and only passes on an answer whose citations match what was really read. Separately, a plain collector reads the same pods straight from Kubernetes for the table, so the view does not depend on the model. Both produce the same "evidence" shape, which always says who was asked, when, how completely, and what went wrong. Nothing can write to the cluster, the browser chooses nothing but the question, and telemetry records that things happened without recording what was said.

## Run the app

You need the Kind cluster `vyom` with the MCP server installed. If it is not there yet, see [local development](../docs/LOCAL_DEVELOPMENT.md).

```sh
# once per cluster (safe to re-run): MCP server, collector identity, demo pods
./scripts/vyom-up.sh     # since S1.7 this installs the whole Vyom chart; before that it applied plain MCP manifests

# terminal 1: the backend, wired to Kind. Needs the model key for chat; the pods page works without it.
export OPENROUTER_API_KEY=...        # or put the key in .local/model-api-key with mode 600
./scripts/dev-up.sh                  # API on http://127.0.0.1:8000; leave it running

# terminal 2: the UI
cd frontend && npm ci && npm run dev # http://127.0.0.1:5173
```

Open http://127.0.0.1:5173 for Today (ask a question) and http://127.0.0.1:5173/kubernetes for the pods table.

`dev-up.sh` issues tokens that last one hour. When chat or the table starts reporting that a credential was rejected, stop it with Ctrl-C and start it again.

The two live checks, if you want to see every rule exercised (both spend a few model requests):

```sh
./scripts/chat-check.sh
./scripts/pods-check.sh
```

## Earlier exercises

These came before the guides and are independent of the Vyom code.

| Directory | What it is |
|---|---|
| [langchain-basics/](langchain-basics/README.md) | One Python file: a model, tools and a hand-written tool loop against a Kind cluster |
| [langgraph-basics/](langgraph-basics/README.md) | The same loop rebuilt as a LangGraph graph. Guide 2 assumes you have done this one |
| [kind-chat/](kind-chat/README.md) | An early two-cluster chat proof of concept with direct Kubernetes reads and Helm charts. Vyom's real implementation does not reuse it |

Their `.venv` directories were created when this folder was called `poc/`; recreate them before running anything there.
