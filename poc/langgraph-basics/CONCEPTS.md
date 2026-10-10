# LangGraph concepts

LangGraph is a runtime for programs whose control flow is a graph over saved state. You describe the steps (nodes), what may follow what (edges) and the data they share (state). The runtime executes it, saves the state after every step, and can therefore stop, resume, replay and stream.

It does not replace LangChain. Models, messages, prompts and tools are still LangChain objects; section 0 of [`graph_agent.py`](graph_agent.py) is copied from the first exercise. LangGraph replaces only the part you wrote by hand there: the loop.

- **Part 1** (sections 1–7) follows `graph_agent.py`. The numbers match the section comments in the code.
- **Part 2** (sections 8–19) covers the rest of LangGraph.
- **Part 3** (section 20) is what this means for Vyom's sprint 1.

API names were checked against `langgraph` 1.2.

---

# Part 1: the fundamentals, as used in `graph_agent.py`

## The loop, then and now

`agent.py`:

```python
for _ in range(MAX_STEPS):
    reply = chain.invoke(...)          # ask the model
    messages.append(reply)
    if not reply.tool_calls:           # decide
        return reply
    for call in reply.tool_calls:      # run tools
        messages.append(tool.invoke(call))
```

`graph_agent.py` splits those three things apart and names them:

```text
            ┌───────────────────────────────────────────────┐
            ▼                                               │
START ─▶ model ──route_after_model──▶ tools ────────────────┤
            │            │                                  │
            │            └──▶ approval ──approve──▶ tools   │
            │                     │                         │
            │                     └──reject──▶ model ───────┘
            ▼
           END
```

Asking the model is a node. Running tools is a node. The `if` is a routing function on an edge. The `messages` variable is the state. Once they are separate, the runtime can save between any two of them, which is where every other feature comes from.

## 1. State

State is a typed dict that every node receives. It is the single source of truth for a run.

```python
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_rounds: int
```

Nodes never mutate state. They **return an update**: a dict with only the keys they want to change. The runtime merges it. How it merges is decided per key:

- **No annotation: replace.** `{"tool_rounds": 3}` overwrites the old value. Last write wins.
- **With a reducer: combine.** `Annotated[list, add_messages]` names a function `(old, update) -> new`. `add_messages` appends, so a node returns only its new messages.

Reducers are what make partial updates and parallel nodes safe: two nodes can both return `{"messages": [...]}` in the same step and both are kept.

`add_messages` does a little more than append. It matches on message `id`: an update carrying an existing ID replaces that message, and a `RemoveMessage(id=...)` deletes it. That is how history is edited or trimmed inside a graph.

`MessagesState` is a ready-made state with just the `messages` key. `graph_agent.py` defines its own to show a second key.

Design advice: keep state small and explicit. Put in it what later steps need to decide or answer (messages, collected evidence, counters, the user's scope). Do not put clients, connections or secrets in it: state is serialised and stored.

## 2. Nodes

A node is a function `(state) -> update`. `call_model` and `run_tools` are the two halves of the old loop body, unchanged in substance.

Properties worth knowing:

- A node does not know its neighbours. It can be tested alone by passing it a dict.
- A node is one **step**. The runtime saves state after it. If the process dies during a node, that node runs again on resume; completed nodes do not.
- So a node should be safe to re-run, or small enough that re-running is cheap. A node that makes three API calls and crashes on the third repeats all three.
- A node can be any callable or Runnable, including another compiled graph (section 14).

## 3. Edges and routing

Edges decide what runs next.

- **Fixed edge**: `add_edge("tools", "model")`. Always.
- **Conditional edge**: `add_conditional_edges("model", route_after_model)`. After `model`, call the function with the state; it returns the name of the next node, or `END`.
- **Entry**: `add_edge(START, "model")`.

`route_after_model` is the old `if not reply.tool_calls`, with one more branch. It is ordinary code reading state, and that matters: the model chooses which tools to request, but the model never chooses where the graph goes. The rule "log reads go through approval" lives in routing, so no prompt can argue its way past it.

The `Literal[...]` return annotation tells LangGraph the possible destinations, which is how `/graph` can draw the dotted arrows.

A cycle is just an edge that points backwards. The loop that LCEL could not express is `tools → model`.

## 4. Human approval: `interrupt` and `Command`

```python
decision = interrupt({"question": "Allow these tool calls?", "calls": sensitive})
```

`interrupt(value)` pauses the graph inside a node. Three things happen:

1. The current state is saved by the checkpointer, marked as waiting at this node.
2. `stream()` or `invoke()` returns to the caller. The `value` comes back with it (as an `__interrupt__` entry) so the caller can show it to a person.
3. Nothing is left running. The pause is data in storage, which is why killing the process during the prompt (README step 7) loses nothing.

To continue, the caller runs the graph again on the same thread with `Command(resume=answer)`. The interrupted node **starts again from its first line**, and this time `interrupt()` returns `answer`.

That restart rule is the one thing people get wrong:

- Code above `interrupt()` runs twice. Keep it free of side effects. `approval` only reads state before interrupting.
- This is also why approval is its own node and not a line inside `run_tools`: there, any tools already executed in that node would run again on resume.
- Interrupts require a checkpointer. Without saved state there is nothing to resume.

**`Command`** has two jobs, and `graph_agent.py` uses both:

- As **input**, `Command(resume=value)` answers a pending interrupt.
- As a node's **return value**, `Command(goto="tools", update={...})` combines a state update with the choice of next node. It is an alternative to a conditional edge when the node itself knows where to go. `approval` returns `goto="tools"` on yes, and on no returns `goto="model"` with denial messages.

Why denial writes a `ToolMessage` for every call in the batch: providers reject a conversation where a tool request has no result. A refusal is a result.

## 5. Compile, checkpointer, threads

`builder.compile(checkpointer=...)` validates the graph (unknown nodes, unreachable parts) and returns a Runnable with `invoke`, `stream` and their async forms.

A **checkpointer** saves a snapshot of the state after every step. A **thread** is the key the snapshots are filed under:

```python
run_config = {"configurable": {"thread_id": "default"}}
app.invoke({"messages": [HumanMessage("...")]}, run_config)
```

On each call the runtime loads the thread's latest checkpoint, merges your input into it through the reducers, runs, and saves as it goes. That is why `main()` passes only the new question: the rest of the conversation is already there.

What this gives you:

- **Conversation memory** across calls and restarts (README step 6).
- **Pause and resume** (section 4).
- **Fault tolerance**: after a crash, a run continues from the last saved step.
- **History**: every step is kept, not just the latest (section 7).

Checkpointers are swappable: `InMemorySaver` for tests and learning (lost on exit), `SqliteSaver` for a local file as used here, `PostgresSaver` for real deployments with several replicas.

What it costs: a thread grows without bound unless you trim it, every step is a write, and the store now holds user conversations and tool output. In a multi-user system the thread must be tied to the authenticated user and workspace on the server; a `thread_id` taken from the browser is a way to read someone else's conversation.

## 6. Running and streaming

`invoke` returns the final state. `stream` yields as the run progresses, in a mode you choose:

| `stream_mode` | Yields | Use |
|---|---|---|
| `"updates"` | `{node_name: update}` after each node | Progress display. Used in `drive()` |
| `"values"` | The full state after each step | Simple UIs, debugging |
| `"messages"` | Model tokens as generated, with metadata saying which node | Typing effect |
| `"custom"` | Anything a node emits through a stream writer | Progress from inside a long tool |
| `"debug"` | Detailed task and checkpoint events | Diagnosing the runtime |

You can pass a list of modes and get `(mode, chunk)` pairs. `"messages"` works even when the node calls `model.invoke`: the runtime listens to the model through callbacks.

`drive()` is the standard shape of an application around an interruptible graph: stream; if an `__interrupt__` arrived, get the human's answer and stream again with `Command(resume=...)`; repeat until a stream ends without one. In a web app the two halves are separate HTTP requests, possibly days apart, joined only by `thread_id`.

Two bounds exist on a run. `recursion_limit` in the config is the runtime's hard cap on steps and raises `GraphRecursionError`. `tool_rounds` in state is this app's own softer budget, which tells the model to wrap up. Have both.

## 7. Looking inside: state, history, time travel

- `app.get_state(config)` returns the latest snapshot: `.values` (the state), `.next` (nodes due to run; empty when finished), `.interrupts` (pending pauses). `main()` uses it at startup to detect a paused thread.
- `app.get_state_history(config)` returns every checkpoint, newest first. `/history` prints it.
- `app.get_graph().draw_mermaid()` draws the structure.

Because every step is saved, you can go back. Running the graph with `None` as input and an old checkpoint's config **replays from that point as a new branch**. The original history is kept.

```python
history = list(app.get_state_history(run_config))
before_approval = next(s for s in history if s.next == ("approval",))
for chunk in app.stream(None, before_approval.config, stream_mode="updates"):
    print(chunk)          # stops at the approval interrupt again: answer differently this time
```

`app.update_state(config, {...})` edits a checkpoint's state by hand before continuing, for example to correct a tool argument a human disagreed with. Replay and edit together are how you debug an agent: rewind to just before it went wrong, change one thing, run forward.

---

# Part 2: the rest of LangGraph

## 8. The execution model

A run proceeds in **supersteps**. In each one, the runtime takes all nodes that are due, runs them (concurrently if there are several), collects their updates, applies the updates through the reducers, saves a checkpoint, and uses the edges to work out which nodes are due next. It ends when none are.

Consequences:

- Nodes in the same superstep see the same input state. None sees another's update until the next step.
- Updates in a superstep are applied together. If one parallel node raises, the whole step fails and none of its updates are applied; successful siblings are remembered so they are not re-run on resume.
- "Step" in `/history` and in `recursion_limit` means superstep.

## 9. More on state

- **Input and output schemas.** `StateGraph(State, input_schema=..., output_schema=...)` lets the graph accept and return a narrower shape than it uses internally, keeping scratch keys private.
- **Pydantic or dataclass state** works as well as `TypedDict`, with validation on input.
- **Custom reducers** are any `(old, new) -> merged` function: `operator.add` for lists and counters, or your own to merge dicts or keep the newest evidence per resource.
- **Managing message growth**: trim before the model call inside the node (state keeps everything, the model sees a window), or delete with `RemoveMessage`, or summarise old turns into one message stored in a `summary` key.

## 10. Runtime context: values that are not state

Some values belong to one run but should not be saved or shown to the model: the authenticated user, a workspace ID, a database handle. Declare a `context_schema` on the graph and pass `context={...}` at invoke time; nodes and tools read it from the runtime object. This is LangGraph's form of the injected arguments described in the LangChain exercise, and it is where server-supplied scope belongs. `graph_agent.py` uses a `NAMESPACE` constant for the same purpose.

## 11. Errors, retries and durability

- **Retry policy per node**: `add_node("model", call_model, retry_policy=RetryPolicy(max_attempts=3))` retries on transient exceptions with backoff. Appropriate for model and network calls.
- **Timeouts** can also be set per node.
- **Resuming after failure**: invoke the same thread again with `None` as input and the run continues from the last checkpoint.
- **Durable execution** is the name for this property. It holds only as far as your nodes are safe to re-run. Reads are. A node that sends an email is not, unless it checks whether it already did.
- **Tool errors** are still your design choice: return them as `ToolMessage` text so the model can react (as here), or raise and let a retry policy handle it.

## 12. Human-in-the-loop patterns

`interrupt` supports more than yes or no. The resume value can be anything:

- **Approve or reject** a proposed action (this exercise).
- **Edit**: return corrected tool arguments and run with those.
- **Ask**: a tool named something like `ask_user` that interrupts with a question and returns the reply as its result, letting the model request clarification.
- **Review state** at a fixed point before continuing.

`compile(interrupt_before=["tools"])` is an older, static way to stop before a named node. It is useful for debugging; `interrupt()` is preferred because it can carry a payload and sit behind a condition.

## 13. Branching and parallelism

- **Fan-out**: several edges leaving one node run their targets in the same superstep. Their updates merge through reducers, so any key they both write needs one.
- **Fan-in**: a node with several incoming edges runs once they have completed.
- **`Send`** creates a dynamic number of branches. A routing function returns `[Send("check_namespace", {"ns": n}) for n in namespaces]`; each runs the target node with its own input. This is map-reduce: fan out over a list discovered at run time, reduce through a reducer.

For Vyom, the obvious use is collecting from several sources at once (pods, deployments, events, metrics) and joining the evidence before the model sees it.

## 14. Subgraphs and multi-agent systems

A compiled graph is a Runnable, so it can be a node in another graph. Uses:

- **Encapsulation**: a "diagnose" subgraph with private state, exposing only its result.
- **Reuse**: the same approval subgraph in several agents.
- **Multi-agent**: each agent is a subgraph. A supervisor node routes between them, or agents hand off with `Command(goto="other_agent", graph=Command.PARENT)`.

If the subgraph shares state keys with its parent, it reads and writes them directly. If not, wrap it in a node function that translates in and out. Checkpointing and interrupts work through subgraphs.

Multi-agent designs multiply cost and failure modes. Use one when a single agent's tools or instructions have grown past what it handles well, not as a starting point.

## 15. Long-term memory: the Store

A checkpointer remembers **within a thread**. A **Store** remembers **across threads**: a namespaced key-value store, optionally with semantic search, passed at `compile(store=...)`. Nodes read and write it through the runtime.

Typical use: `("users", user_id, "preferences")` holds facts that every new conversation with that user should start with. The namespace is the access boundary, so it must be built from authenticated identity.

## 16. Prebuilt pieces

- **`ToolNode(tools)`**: runs all tool calls in the last AI message, in parallel, with error handling. It is `run_tools` without the budget.
- **`tools_condition`**: routes to `"tools"` if the last message has tool calls, otherwise to `END`. It is `route_after_model` without the approval branch.
- **`create_agent`** (in the `langchain` package): builds the model/tools graph for you and accepts a `checkpointer`. Its `HumanInTheLoopMiddleware` is the approval node of this exercise as configuration: name the tools that need review.

Having written the three by hand, treat the prebuilts as shortcuts whose behaviour you can predict, and drop back to a custom graph when you need a branch they do not have.

## 17. The functional API

The same runtime has a second syntax with no explicit graph. `@entrypoint(checkpointer=...)` marks a function as a workflow and `@task` marks functions whose results are checkpointed; ordinary `if` and `for` provide the control flow, and `interrupt` works inside.

It suits code that reads naturally as a procedure. The graph API suits flows you want to see, draw and route explicitly. They can call each other.

## 18. Async and serving

Every method has an async form (`ainvoke`, `astream`, `aget_state`), and nodes can be `async def`. A web backend should use them, with an async checkpointer, so one slow model call does not block other requests.

Serving a graph over HTTP is your choice. A FastAPI endpoint that calls `app.astream(...)` and forwards chunks as server-sent events is enough. LangGraph also offers its own server and hosted platform, with thread and run APIs built in; nothing in the library requires them.

## 19. Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Returning the whole message list from a node | History doubles each step | Return only new messages; the reducer appends |
| Mutating `state` in place | Changes vanish or appear inconsistently | Return an update dict |
| Two parallel nodes writing a key with no reducer | `InvalidUpdateError` | Add a reducer, or have only one writer |
| Side effects above `interrupt()` | They happen twice | Move them below, or into a later node |
| `interrupt()` with no checkpointer | Error at run time | Compile with one |
| A tool request left without a `ToolMessage` | Provider rejects the next model call | Always answer every tool call, including refusals |
| Same `thread_id` for different users | Conversations leak between them | Derive the thread from authenticated identity |
| Clients or secrets in state | Serialisation errors, or secrets in the database | Use runtime context |
| No `recursion_limit` thought | A looping model burns tokens until the default cap | Set a limit that fits the task and add a soft budget |
| Never trimming a thread | Cost and latency climb with every turn | Window, summarise or expire history |

---

# Part 3: what this means for Vyom

## 20. From this exercise to sprint 1

Sprint 1 specifies a LangGraph MCP host calling tools on an upstream Kubernetes MCP server. Mapping what you have built onto that:

| Here | Sprint 1 |
|---|---|
| Four `@tool` functions in the same file | Tools listed from the MCP server and wrapped as LangChain tools; the host chooses which to expose |
| `NAMESPACE` constant | Server-supplied scope through runtime context, never from the model or browser |
| `route_after_model` and `NEEDS_APPROVAL` | Host-side allowlist and argument validation before any call leaves the process |
| `tool_rounds`, `recursion_limit` | The required limits on calls, time and output |
| `run_tools` truncating output | Result validation and bounding of what the server returns |
| `stream_mode="updates"` | Progress events to the chat UI, and the spans of an owned-component trace |
| `SqliteSaver` | **Not in sprint 1.** The working agreement says no persistent graph state yet |

That last row has a consequence. Without a checkpointer there are no interrupts and no memory across requests, so sprint 1's graph is a single-request loop: the browser sends recent history, as the Kind chat POC already does, and nothing pauses. If conversation memory within a session is wanted before persistence is allowed, `InMemorySaver` is the non-persistent option, and whether that counts as "persistent graph state" is a decision for you, not something to assume.

One difference to keep in mind: this exercise added a log tool because it makes the approval demo meaningful on a throwaway cluster. The Vyom agreement does not authorise agent pod-log tools, so that tool does not carry over.

### One-paragraph summary

A LangGraph program is state, nodes that return updates to it, and edges that choose the next node. The runtime saves the state after every step under a thread ID. From that one mechanism come memory, pause and resume, recovery, replay and streaming. The model's freedom is confined to what it asks for inside a node; where the graph goes next is your code. Keep nodes small and safe to re-run, keep state small and explicit, bound every loop twice, and tie threads to real identity.
