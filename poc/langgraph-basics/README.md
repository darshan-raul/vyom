# LangGraph basics: the same agent as a graph

The second learning exercise, also separate from the Vyom plan and `poc/kind-chat/`. It takes the tool loop you wrote by hand in [`../langchain-basics/agent.py`](../langchain-basics/agent.py) and rebuilds it with LangGraph, then adds what the loop could not do: conversations that survive a restart, a pause for human approval, and step-by-step streaming.

- [`graph_agent.py`](graph_agent.py): the whole app. Section 0 is the LangChain part you know; sections 1–7 are new.
- [`CONCEPTS.md`](CONCEPTS.md): LangGraph explained, numbered to match the code.
- [`rbac-logs.yaml`](rbac-logs.yaml): one extra permission, for the new log tool.

It uses the cluster, workloads and kubeconfig from the first exercise. Run everything from `poc/langgraph-basics/`.

## What is different from `agent.py`

| | `agent.py` | `graph_agent.py` |
|---|---|---|
| Control flow | a `for` loop and an `if` | nodes and edges |
| Conversation | a list in a variable, lost on exit | saved to `.private/threads.db` per thread |
| Tools | 3, all run immediately | 4; `get_pod_logs` waits for your approval |
| Progress | `print` inside the loop | streamed by the runtime, one update per node |

## 1. Prepare the cluster

The `lc-basics` cluster from the first exercise must be running (`kind get clusters`). If you deleted it, redo steps 1 and 2 of [`../langchain-basics/README.md`](../langchain-basics/README.md) first.

Grant the reader identity permission to read pod logs, and give it a fresh token (the one from last time was valid for 8 hours):

```sh
kubectl --context kind-lc-basics apply -f rbac-logs.yaml

KC=../langchain-basics/.private/kubeconfig
TOKEN=$(kubectl --context kind-lc-basics -n shop create token agent-reader --duration=8h)
kubectl config --kubeconfig $KC set-credentials agent-reader --token="$TOKEN"
```

Check that the identity can now read logs, and still cannot change anything:

```sh
kubectl --kubeconfig $KC get pods
kubectl --kubeconfig $KC logs $(kubectl --kubeconfig $KC get pods -o name | grep worker) --tail=3   # "cannot reach queue"
kubectl --kubeconfig $KC delete pod --all                                                           # Forbidden
```

## 2. Install

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

New compared with last time: `langgraph` (the graph runtime) and `langgraph-checkpoint-sqlite` (saves graph state to a SQLite file).

## 3. Run

```sh
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY
.venv/bin/python graph_agent.py            # thread "default"
.venv/bin/python graph_agent.py monday     # a separate conversation called "monday"
```

## 4. A guided session

Do these in order. Each one shows a LangGraph feature; the section number points into `CONCEPTS.md`.

| # | Do this | What to notice | Concept |
|---|---|---|---|
| 1 | Type `/graph` | The control flow, drawn from the code. Dotted arrows are decisions | 3, 5 |
| 2 | Ask `what is running here?` | `[model]` and `[tools]` lines arrive one node at a time | 2, 6 |
| 3 | Ask `why is the worker failing? read its logs` | The graph stops at `[approval needed]`. Answer `y`. The log line `cannot reach queue` reaches the model | 4 |
| 4 | Ask `read the worker logs again`, answer `n` | The model is told the call was denied and answers without it | 4 |
| 5 | Type `/history` | One checkpoint per step. Find the rows where `next=('approval',)` | 5, 7 |
| 6 | Press Enter on an empty line to quit, then start it again | `Thread 'default': N saved messages`. Ask `what did we find out about the worker?` and it answers from memory | 5 |
| 7 | Ask for the logs again and, at the `allow?` prompt, press **Ctrl-C** | The process dies while the graph is paused | 4 |
| 8 | Start it again | `This thread was paused waiting for approval`. Answer `y` and the run continues from where it stopped | 4, 5 |
| 9 | Quit, run `.venv/bin/python graph_agent.py other` | A different thread: zero saved messages, no knowledge of the first conversation | 5 |

Steps 7 and 8 are the ones to think about. No process was waiting. The pause was a row in a database.

To see that database:

```sh
sqlite3 .private/threads.db "select thread_id, count(*) from checkpoints group by 1"
```

## 5. Experiments in the code

1. **No checkpointer.** Change the compile line to `app = builder.compile()`. `get_state` and the approval pause now fail: both need saved state. (Restore it afterwards.)
2. **More approvals.** Add `"list_events"` to `NEEDS_APPROVAL`. No other change is needed; routing reads that set.
3. **Tight budget.** Set `MAX_TOOL_ROUNDS = 1` and ask why the worker is failing. Watch the `tool budget` message reach the model.
4. **Runtime step cap.** Set `"recursion_limit": 3` in `main()`. A question that needs tools now raises `GraphRecursionError`. That is the runtime's backstop; `tool_rounds` is the polite version.
5. **Prebuilt node.** Replace `run_tools` with `from langgraph.prebuilt import ToolNode` and `builder.add_node("tools", ToolNode(TOOLS))`. It works, and you lose the budget, because the prebuilt node knows nothing about `tool_rounds`.
6. **Token streaming.** In `drive`, try `stream_mode="messages"` and print each chunk: `for message, meta in app.stream(...): print(message.text, end="", flush=True)`. You get the model's tokens as they are generated, even though `call_model` uses `invoke`.
7. **Time travel.** `CONCEPTS.md` section 7 has a short snippet that re-runs the conversation from an earlier checkpoint.

## Clean up

```sh
rm -rf .private .venv                                     # saved conversations and the environment
kubectl --context kind-lc-basics delete -f rbac-logs.yaml # remove the log permission
kind delete cluster --name lc-basics                      # only when you are done with both exercises
```

`.private/threads.db` holds every message of every thread, including any log lines you approved. Delete it when you are done.
