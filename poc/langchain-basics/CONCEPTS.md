# LangChain concepts

LangChain is a library of small, standard pieces for building applications around a language model. The model itself is a remote HTTP API that takes a list of messages and returns one message. Everything else (prompts, tools, memory, retrieval, "agents") is ordinary code around that one call.

This file has three parts:

- **Part 1** (sections 1–7) explains what [`agent.py`](agent.py) does. The numbers match the section comments in the code. Read it with the code open.
- **Part 2** (sections 8–22) covers the rest of LangChain: every concept you will meet in its docs and in other people's code.
- **Part 3** (section 23) is what LangChain's building blocks cannot express, and what LangGraph adds.

API names were checked against `langchain` 1.4, `langchain-core` 1.4–1.6 and `langgraph` 1.2. The library moves quickly; concepts change far more slowly than import paths.

---

# Part 1: the fundamentals, as used in `agent.py`

## First: everything is a message

A chat model never sees "a conversation". It sees a list of messages, sent in full on every request. LangChain has four message types, and `agent.py` uses all of them:

| Type | Written by | Contains |
|---|---|---|
| `SystemMessage` | you, the developer | Standing instructions: role, rules, scope |
| `HumanMessage` | the user | The question |
| `AIMessage` | the model | Text in `.content`, **or** requests in `.tool_calls`, or both |
| `ToolMessage` | your code | The output of one tool, tagged with the `tool_call_id` it answers |

One question about the failing worker produces this list. Reading it is the fastest way to understand what an agent is:

```text
System   You are a read-only Kubernetes assistant for the namespace 'shop' ...
Human    why is the worker failing?
AI       tool_calls: [list_pods()]                          <- no text, just a request
Tool     web-…  phase=Running … / worker-…  phase=Running  ready=0/1  restarts=7 …
AI       tool_calls: [get_pod_details(pod_name="worker-…")]
Tool     container=worker  state=waiting reason=CrashLoopBackOff  last_exit_code=1 …
AI       The worker pod is in CrashLoopBackOff: its container exits with code 1 …
```

The model was called three times. Each call received everything above it.

## 1. Tools

A tool is a Python function plus a description the model can read. The `@tool` decorator builds that description from the function itself:

```python
@tool
def get_pod_details(pod_name: str) -> str:
    """Show one pod's containers: image, current state, ..."""
```

becomes this JSON, which is sent to the provider with every request:

```json
{"type": "function", "function": {
  "name": "get_pod_details",
  "description": "Show one pod's containers: image, current state, ...",
  "parameters": {"type": "object",
                 "properties": {"pod_name": {"type": "string"}},
                 "required": ["pod_name"]}}}
```

Three consequences:

- **The docstring is prompt text.** The model chooses tools by reading descriptions. "Call this first to see what exists" in `list_pods` is an instruction to the model.
- **Type hints are the contract.** `pod_name: str` makes the argument required; `pod_name: str = ""` in `list_events` makes it optional. Arguments the model sends are validated against this schema before your function runs.
- **The return value is model input.** Whatever string you return is appended to the conversation. Keep it short and factual, and return errors as text so the model can explain them. `list_events` caps both the number of events and the message length for this reason.

Tools are also where authority lives. The model can only cause what your tools can do. Here that is three read calls in one hard-coded namespace, using a token that the cluster itself limits to those reads.

## 2. Chat model

`ChatOpenAI` is LangChain's wrapper for any server that speaks the OpenAI Chat Completions format. OpenRouter speaks that format for many providers, so `base_url="https://openrouter.ai/api/v1"` is enough to reach a Claude model with this class. Other providers have their own classes (`ChatAnthropic`, `ChatBedrockConverse`, …) with the same methods, which is the point of the abstraction: the rest of `agent.py` would not change.

`model.invoke(messages)` sends one HTTP request and returns one `AIMessage`. The model keeps nothing between calls.

## 3. `bind_tools`: the model asks, your code acts

This is the idea most worth getting right. `model.bind_tools(TOOLS)` returns a copy of the model that attaches the tool schemas to each request. It does not let the model execute anything.

With tools attached, the model has two ways to reply:

- plain text in `.content`, or
- a structured request in `.tool_calls`, such as `{"name": "get_pod_details", "args": {"pod_name": "worker-abc"}, "id": "call_1"}`.

A tool call is the model saying "please run this and tell me the result". Whether it runs, with what checks, and what comes back are entirely up to the code in section 6. That gap between asking and acting is where every safety control in a real system sits: allowlists, argument validation, limits and permissions.

## 4. Prompt template

`ChatPromptTemplate` is a message list with holes:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "... for the namespace '{namespace}'. ..."),
    MessagesPlaceholder("messages"),
])
```

`{namespace}` is filled with a string. `MessagesPlaceholder("messages")` is filled with an entire list of messages, which is how the running conversation gets spliced in after the system message. `prompt.invoke({"namespace": "shop", "messages": [...]})` returns the finished list.

Templates keep instructions in one place and separate from data. They are a convenience: you could build the same list by hand.

## 5. Chains and the `|` operator

```python
chain = prompt | model_with_tools
```

Prompts, models and tools all implement one interface called **Runnable**: `.invoke(input)` for one result, `.stream(input)` for chunks as they arrive, `.batch([...])` for many inputs. Because they share it, `|` can connect them: the output of the left side becomes the input of the right side. `chain.invoke(x)` is the same as `model_with_tools.invoke(prompt.invoke(x))`.

This composition style is called LCEL (LangChain Expression Language). It is good for fixed pipelines: fill prompt, call model, parse output. It cannot express "repeat until done", which is why the next section is a plain Python loop. Section 9 covers Runnables fully.

## 6. The agent loop

An agent is a model, a set of tools and a loop:

```text
            ┌──────────────────────────────────────┐
            ▼                                      │
   send all messages to the model                  │
            │                                      │
   reply has tool_calls? ── yes ─▶ run each tool, append a ToolMessage
            │ no
            ▼
   return the text answer
```

The model decides which tools to call, in what order, and when it has seen enough. Your code decides everything else. Details in `answer()` worth noticing:

- The `AIMessage` holding the tool requests is appended **before** the results. Each `ToolMessage` points back at it through `tool_call_id`; providers reject a tool result with no matching request.
- One reply can request several tools. Each gets its own `ToolMessage`.
- `MAX_STEPS` bounds the loop. Without a limit, a model that keeps asking for tools runs (and bills) indefinitely.
- An unknown tool name gets an error message back instead of an exception, so the model can correct itself.
- `selected.invoke(call)` takes the whole tool-call dict, validates the arguments, runs the function and returns a ready-made `ToolMessage`.

## 7. Memory is a list

`main()` keeps one `messages` list for the whole session and appends every question, tool request, tool result and answer to it. That list is the only reason "and the reports one?" works as a follow-up.

Two things follow. History costs tokens: the `[tokens] in=` number rises every turn because the full list is resent, including old tool outputs. And history is trusted no more than any other input: the model treats old messages as context, so anything a tool once returned stays in front of it. Real applications trim, summarise or store history; this one forgets it on exit.

---

# Part 2: the rest of LangChain

## 8. The package map

"LangChain" is several packages. Knowing which is which explains most import lines.

| Package | What it holds |
|---|---|
| `langchain-core` | The abstractions: Runnable, messages, prompts, tools, output parsers, documents, base classes for models, embeddings, vector stores and retrievers. No provider code. `agent.py` uses this |
| `langchain-openai`, `langchain-anthropic`, `langchain-aws`, … | One package per provider. Each implements the core base classes for that provider's API |
| `langchain` | The high-level layer: `create_agent`, agent middleware, `init_chat_model`. Built on LangGraph |
| `langgraph` | The graph runtime: state, nodes, edges, persistence, interrupts (section 23) |
| `langchain-text-splitters` | Document chunking for retrieval |
| `langchain-community` | Community-maintained integrations of varying quality |
| `langchain-classic` | The pre-1.0 chains, memory classes and `AgentExecutor`, kept for old code |
| `langchain-mcp-adapters` | Turns tools served by MCP servers into LangChain tools |
| `langsmith` | Client for LangSmith, the hosted tracing and evaluation service. Installed as a dependency of core |

What to `pip install`, in practice:

- Start with `langchain-core` plus the one provider package for the API you call. That covers prompts, models, tools and chains, and it is all `agent.py` uses (see `requirements.txt`).
- Add the package named `langchain` only when you want the tool loop written for you (`create_agent`) instead of writing it yourself as `answer()` does. Despite its name, that package is not "all of LangChain"; it is the agent layer on top.
- Add `langgraph` when you need to design the control flow yourself.

## 9. Runnables in full

`Runnable` is the single most important abstraction in LangChain. Nearly every object is one: prompt templates, chat models, output parsers, retrievers, tools, and any chain made of them. A compiled LangGraph graph is one too.

### The interface

| Method | Does |
|---|---|
| `invoke(input)` | One input, one output |
| `stream(input)` | Yields output chunks as they are produced |
| `batch([inputs])` | Runs many inputs concurrently (a thread pool by default) |
| `ainvoke`, `astream`, `abatch` | The same, as coroutines for `asyncio` code |
| `astream_events(input)` | Yields a typed event for every step inside a chain: model start, token, tool end and so on |

You write `invoke` logic once and get the others. That uniformity is why a chain of five parts can be streamed or batched with no extra code.

Each Runnable also knows its input and output types (`chain.input_schema`, `chain.output_schema`), which is how tools get JSON schemas and how graphs get drawn.

### Composition primitives

Five building blocks cover almost everything:

```python
from operator import itemgetter
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough, RunnableBranch

# 1. Sequence: output of each step feeds the next.
chain = prompt | model | parser

# 2. Parallel: run several Runnables on the SAME input, get a dict of results.
both = RunnableParallel(summary=summarise_chain, keywords=keyword_chain)

# 3. Lambda: wrap any function so it can sit in a chain.
shout = RunnableLambda(lambda text: text.upper())

# 4. Passthrough: forward the input unchanged; .assign adds keys to a dict.
with_context = RunnablePassthrough.assign(context=itemgetter("question") | retriever)

# 5. Branch: pick one of several Runnables by a condition.
route = RunnableBranch((lambda x: "logs" in x["question"], logs_chain), default_chain)
```

**Coercion** makes this terse. Inside a `|` expression, a plain `dict` becomes a `RunnableParallel` and a plain function becomes a `RunnableLambda`. So this is a complete retrieval chain:

```python
chain = {"context": retriever, "question": RunnablePassthrough()} | prompt | model | StrOutputParser()
```

The dict runs the retriever and the passthrough on the same input string, producing `{"context": [...], "question": "..."}`, which is exactly what the prompt template needs.

### Modifiers

Every Runnable has methods that return a new, wrapped Runnable. None of them change the original.

| Method | Effect |
|---|---|
| `.bind(**kwargs)` | Fixes arguments for every call. `bind_tools` is a specialised `bind` |
| `.with_retry(stop_after_attempt=3)` | Retries on exceptions with backoff |
| `.with_fallbacks([other])` | If this fails, try `other` with the same input |
| `.with_config(...)` | Attaches tags, metadata, callbacks or a run name |
| `.with_structured_output(Schema)` | On chat models: return a parsed object instead of a message (section 14) |
| `.configurable_fields(...)`, `.configurable_alternatives(...)` | Exposes a setting, or a whole swappable component, to be chosen per call |
| `.map()` | Applies the Runnable to each element of a list |

### Config

The optional second argument to every method is a `RunnableConfig`, a dict that travels down through every step of a chain automatically:

```python
chain.invoke(x, config={"tags": ["prod"], "metadata": {"user": "u1"}, "callbacks": [handler],
                        "max_concurrency": 4, "configurable": {"thread_id": "abc"}})
```

`tags` and `metadata` label traces. `callbacks` observe execution (section 19). `configurable` carries per-call values such as LangGraph's `thread_id`. `recursion_limit` bounds graph steps.

### What LCEL is and is not

LCEL builds a **directed acyclic graph**: data flows left to right, possibly fanning out and back in, and then it ends. It has no loop, no shared mutable state and no way to stop and resume. For fixed pipelines that is a strength: the flow is visible in one expression and streaming works end to end. For anything where the next step depends on what just happened, repeatedly, it is the wrong tool. Section 23 picks this up.

## 10. Streaming

Models generate one token at a time, so waiting for the whole reply is a choice. `model.stream(messages)` yields `AIMessageChunk` objects. Chunks support `+`: adding them all together gives the same `AIMessage` that `invoke` would have returned, including tool calls, which arrive as partial JSON fragments and are assembled as chunks accumulate.

A chain streams if every step can work on chunks. `prompt | model | StrOutputParser()` streams text token by token. A step that needs the whole input first (a `RunnableLambda` doing `json.loads`, say) blocks streaming at that point.

There are three levels of streaming to distinguish:

- **Tokens** from one model call (`.stream`).
- **Events** from inside a chain (`.astream_events`): which step started, which tool ran.
- **Steps** of an agent or graph: each node's output as it finishes (LangGraph stream modes, section 23).

A chat UI that shows "calling list_pods…" and then types out the answer needs the last two.

## 11. Messages in depth

**Content is not always a string.** `.content` may be a string or a list of content blocks: text, images, audio, files, reasoning, provider-specific blocks. `.text` gives you just the text. `.content_blocks` gives a provider-neutral list of typed blocks, so code written against it works for any provider.

**An `AIMessage` carries more than content:**

| Field | Holds |
|---|---|
| `tool_calls` | Parsed tool requests: `name`, `args`, `id` |
| `invalid_tool_calls` | Requests whose arguments were not valid JSON |
| `usage_metadata` | `input_tokens`, `output_tokens`, `total_tokens`, plus cache and reasoning detail when provided |
| `response_metadata` | Provider facts: model name, finish reason (`stop`, `length`, `tool_calls`) |
| `id` | Unique ID, used for deduplication and for replacing or removing messages in graph state |

A finish reason of `length` means the reply hit `max_tokens` and was cut off. Check it before trusting a truncated answer or parsing truncated JSON.

**Multimodal input** is a `HumanMessage` whose content is a list of blocks, for example a text block and an image block. Whether it works depends on the model.

**Roles are a provider convention.** Some providers want the system prompt as a separate field, some require strict user/assistant alternation, all require each `ToolMessage` to follow the `AIMessage` that requested it. LangChain's model classes translate; they cannot make an invalid sequence valid.

**Managing length.** `trim_messages` cuts a list down to a token budget while keeping it valid (never orphaning a tool result). Summarising old turns into one message is the other common approach.

## 12. Chat models in depth

**One constructor for any provider.** `init_chat_model("anthropic:claude-haiku-5-5")` (in `langchain.chat_models`) returns the right class from a string, which is handy when the model is a configuration value.

**Standard parameters** work across providers: `model`, `temperature`, `max_tokens`, `timeout`, `max_retries`, `stop`, `api_key`, `base_url`. Anything else is provider-specific.

**Tokens and the context window.** Models read and write tokens (roughly three-quarters of a word each). The context window is the maximum tokens in one request: system prompt, tool schemas, whole history and the reply. Everything you send is billed on every call. Most engineering around LLMs is deciding what goes into that window.

**Controlling tool use.** `bind_tools(tools, tool_choice=...)` can force a tool call (`"any"`), force one specific tool by name, or leave it to the model (default). Models may request several tools in one reply; some providers let you turn that off with `parallel_tool_calls=False`.

**Server-side tools.** Some providers run tools themselves (web search, code execution). You bind them like any tool but the provider executes them and returns the result inside the same reply. No loop iteration on your side.

**Reasoning.** Many models can think before answering. The reasoning appears as separate content blocks and its tokens are billed as output. It is enabled and sized with provider-specific parameters.

**Caching and rate limits.** `set_llm_cache(...)` caches identical requests locally, which is useful in development. `InMemoryRateLimiter` passed as `rate_limiter=` throttles calls client-side. Separately, providers offer *prompt caching*: an unchanged prefix (system prompt, tool schemas, old history) is billed at a discount on later calls.

**Legacy "LLMs".** Old tutorials use classes such as `OpenAI` (not `ChatOpenAI`) that take a string and return a string. That is the pre-chat completion API. Use chat models.

**Embedding models** are a different kind of model: text in, a vector of numbers out. They are used for retrieval (section 16), never for conversation.

## 13. Prompts in depth

- `PromptTemplate` produces one string; `ChatPromptTemplate` produces a message list. You will almost always use the second.
- `.partial(namespace="shop")` pre-fills some variables and returns a template needing only the rest.
- **Few-shot prompting** means including worked examples. `FewShotChatMessagePromptTemplate` formats a list of examples as human/AI message pairs. An *example selector* picks the most relevant examples per input, usually by embedding similarity.
- `MessagesPlaceholder` (section 4) is the bridge between templates and history.

Two cautions. A literal `{` in template text must be written `{{`, which bites when you paste JSON into a prompt. And a template is not a security boundary: text substituted into `{question}` can contain instructions, and the model has no reliable way to tell them from yours. Putting untrusted text in a human or tool message rather than the system message helps, and never replaces limiting what tools can do.

## 14. Structured output and output parsers

Often you want data, not prose. There are two generations of solution.

**Modern: `with_structured_output`.** Give the model a schema and get an object back:

```python
from pydantic import BaseModel, Field

class Diagnosis(BaseModel):
    pod: str
    healthy: bool
    cause: str = Field(description="One sentence, based only on observed evidence")

structured = model.with_structured_output(Diagnosis)
result = structured.invoke("worker-abc is in CrashLoopBackOff with exit code 1")  # -> Diagnosis(...)
```

The schema can be a Pydantic class, a `TypedDict` or raw JSON Schema. Underneath it uses either the provider's native JSON-schema mode or a forced tool call whose arguments are your schema. Field names and descriptions are prompt text, exactly like tool docstrings. `include_raw=True` returns the original message alongside the parsed object so you can handle parse failures.

**Older: output parsers.** A parser is a Runnable placed after the model to convert its message into something else. `StrOutputParser` extracts the text and is still the common last step of a chain. `JsonOutputParser` and `PydanticOutputParser` work by adding format instructions to the prompt and parsing whatever text comes back; they are for models without native structured output.

In an agent, structured output is a final step: `create_agent(..., response_format=Diagnosis)` runs the tool loop and then returns a typed result.

## 15. Tools in depth

**Richer schemas.** `@tool(args_schema=MyPydanticModel)` gives per-argument descriptions, enums and validation. `StructuredTool.from_function(...)` builds a tool without the decorator. Subclassing `BaseTool` gives full control.

**Content and artifact.** A tool declared with `response_format="content_and_artifact"` returns a pair: a short string for the model and a full object for your application (a dataframe, raw API response, documents). The artifact rides on the `ToolMessage` but is never sent to the model. This is the standard way to show rich evidence in a UI without paying for it in context.

**Injected arguments.** Some arguments must come from your code, not the model: a user ID, a database handle, a tenant scope. Marking a parameter as injected (`InjectedToolArg`, or the `ToolRuntime` parameter in agents) removes it from the schema the model sees and fills it in at execution time. `agent.py` gets the same effect more crudely with the `NAMESPACE` constant. The principle is identical: authority comes from server context, never from model output.

**Errors.** A tool that raises ends the run unless something catches it. Returning the error as text, as `agent.py` does, or using error-handling middleware lets the model see the failure and adapt.

**Toolkits** are just lists of related tools from one integration.

**MCP.** The Model Context Protocol moves tools into separate server processes. `MultiServerMCPClient` from `langchain-mcp-adapters` connects to servers, lists their tools and returns ordinary LangChain tool objects, which you pass to `bind_tools` or `create_agent` like any others. Nothing in the loop changes: the function call becomes a network call. The host application is still responsible for choosing which servers and tools to expose and for validating what comes back.

**Design advice that matters more than API detail:** few tools with clear, non-overlapping purposes; names and descriptions written for the model; bounded, compact output; errors that say what to do next. Every tool schema is sent on every request, so twenty tools cost tokens and accuracy even when unused.

## 16. Retrieval (RAG)

A model knows only its training data and what is in the request. Retrieval-augmented generation fetches relevant text at question time and puts it in the prompt. LangChain's oldest abstractions exist for this.

**Indexing**, done ahead of time:

```text
source files ──loader──▶ Documents ──splitter──▶ chunks ──embedding model──▶ vectors ──▶ vector store
```

- A `Document` is `page_content` (text) plus `metadata` (source, page, timestamps).
- **Document loaders** read a source (files, web pages, a database) into Documents.
- **Text splitters** cut long documents into chunks, typically a few hundred tokens with some overlap. `RecursiveCharacterTextSplitter` is the default choice. Chunking quality largely decides retrieval quality.
- An **embedding model** maps each chunk to a vector such that similar meanings land close together.
- A **vector store** (Qdrant, pgvector, `InMemoryVectorStore` for learning) stores vectors and finds nearest neighbours.

**Retrieval**, at question time: embed the question, find the nearest chunks, return them. A **retriever** is a Runnable from a query string to a list of Documents, so it composes with `|`. `vector_store.as_retriever()` makes one. Retrievers need not use vectors: keyword search, a SQL query or a hybrid all fit the interface. Metadata filters narrow results (for example to one workspace), and in a multi-tenant system that filter is an access control, not a convenience.

**Two ways to use it:**

- **Two-step RAG**: always retrieve, then answer. One model call, predictable cost. This is the retrieval chain shown in section 9.
- **Agentic RAG**: wrap the retriever as a tool and let the model decide whether and what to search, possibly several times. More flexible, less predictable. It is the same trade-off as `agent.py` versus the Kind chat POC.

Retrieved text is untrusted data. A document can contain instructions; the model may follow them. Cite sources by carrying document IDs through to the answer.

## 17. Memory

"Memory" means two different things.

**Short-term memory** is the message list for the current conversation (section 7). The work is keeping it within the context window: trim old turns, summarise them, or drop bulky tool results once they have been used. In a real application the list must also survive between HTTP requests, so it is stored per conversation ("thread"). LangGraph's checkpointer does this (section 23).

**Long-term memory** is information that outlives one conversation: user preferences, facts learned earlier. It is stored in a database or key-value store and brought in either by putting it in the system prompt or by giving the model tools to search and save it. LangGraph calls its version the Store.

The general name for all of this is **context engineering**: the model only knows what is in the request, so quality depends on putting the right instructions, history, retrieved text and tool results in front of it, and leaving the rest out.

Old tutorials use `ConversationBufferMemory`, `ConversationChain` and `RunnableWithMessageHistory`. These predate LangGraph persistence and are superseded by it.

## 18. Agents: `create_agent` and middleware

`create_agent` in the `langchain` package is the loop from section 6, packaged:

```python
from langchain.agents import create_agent

agent = create_agent(model, tools=TOOLS, system_prompt="You are a read-only Kubernetes assistant ...")
result = agent.invoke({"messages": [{"role": "user", "content": "why is the worker failing?"}]})
result["messages"][-1].text
```

It returns a compiled LangGraph graph with two nodes, model and tools, and it is a Runnable, so `invoke`, `stream` and config all work. Input and output are a state dict whose main key is `messages`. Useful arguments: `response_format` (typed final answer), `checkpointer` (conversation persistence), `middleware`.

**Middleware** is how you customise the loop without rewriting it. A middleware hooks into fixed points:

| Hook | Runs | Typical use |
|---|---|---|
| `before_agent`, `after_agent` | Once per run | Load or save context, final checks |
| `before_model`, `after_model` | Around each model call | Trim history, validate or redact output, stop the run |
| `wrap_model_call` | Around the model call itself | Swap model, retry, fall back, change tools or prompt per call |
| `wrap_tool_call` | Around each tool execution | Authorise, retry, convert errors, log |

Ready-made ones cover the common needs: `SummarizationMiddleware` (compress old history), `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` (the `MAX_STEPS` idea), `HumanInTheLoopMiddleware` (pause for approval before chosen tools), `PIIMiddleware` (redact), `ModelFallbackMiddleware`, `ModelRetryMiddleware`, `ToolRetryMiddleware`, `ContextEditingMiddleware` (clear old tool results).

**Multi-agent** patterns are built from the same parts. The two common ones: a supervisor agent that calls other agents as tools, and handoffs, where one agent passes control to another. Reach for them when one agent's tool list or context gets too large to work well, not before.

**Agent or chain?** Use a fixed chain when you know the steps in advance: it is cheaper, faster and testable. Use an agent when the steps depend on what is discovered along the way. Many good systems are mostly fixed flow with one small agentic part.

## 19. Observability: callbacks, tracing, evaluation

**Callbacks** are the hook system under everything. A callback handler receives events (`on_chat_model_start`, `on_llm_new_token`, `on_tool_start`, `on_tool_end`, `on_chain_error`, …) for every Runnable in a run. Handlers passed in `config` propagate to all nested steps. `astream_events` is the same event stream, exposed as an iterator.

**Tracing** records each run as a tree: the chain, every model call with its exact messages, every tool call with arguments and output, timings and token counts. LangSmith is LangChain's hosted tracer; setting `LANGSMITH_TRACING=true` and an API key turns it on with no code change. That convenience is also a data-governance fact: with it on, your prompts, tool outputs and answers leave your machine. `poc/kind-chat/backend/app.py` wraps its model call in `tracing_context(enabled=False)` for exactly that reason. OpenTelemetry-based tracers are the alternative when traces must stay in your own stack.

**Evaluation** means testing LLM behaviour systematically: a dataset of inputs with expected properties, an evaluator (exact check, heuristic, or another model as judge) and a score tracked across prompt and model changes. Without it you are tuning by anecdote. For agents, evaluate the trajectory (which tools, in what order) as well as the final answer.

## 20. Reliability and cost

Model APIs fail, time out, rate-limit and occasionally return nonsense. The standard controls:

- **Timeouts and retries** on the model (`timeout`, `max_retries`) and on any Runnable (`.with_retry`). Retrying a step with side effects needs care; reads are safe.
- **Fallbacks** to another model or a simpler path (`.with_fallbacks`).
- **Limits** on loop iterations, tool calls, tool output size and total tokens per request.
- **Validation** of model output before acting on it: structured output, finish reason, argument schemas.
- **Concurrency**: `batch` and `max_concurrency` for throughput; async methods in a web server so one slow model call does not block others.

Cost is tokens in plus tokens out, per call, and an agent makes several calls per question, each resending the growing history. The levers are: a smaller model where it suffices, compact tool output, trimming history, fewer tool schemas, and prompt caching for the stable prefix.

## 21. Safety

- **Prompt injection.** Any text the model reads can try to instruct it: user input, retrieved documents, tool output, web pages. There is no complete defence inside the prompt. Assume the model can be talked into requesting any tool call it is able to request.
- **So limit what tools can do.** Least-privilege credentials, read-only where possible, scope fixed by server context, arguments validated, mutations gated by human approval. `agent.py` relies on a Role that permits three read operations, not on the system prompt.
- **Treat output as untrusted.** Do not render model output as HTML, execute it, or use it in a query without the checks you would apply to user input.
- **Mind what leaves the process.** Prompts, tool results and traces go to the model provider and to any tracer you enable. Keep secrets and personal data out of tool output.

## 22. Names from older tutorials

Much LangChain material online predates 1.0. A translation table:

| You will see | It was | Use now |
|---|---|---|
| `LLMChain`, `SequentialChain` | Class-based chains | `prompt \| model \| parser` |
| `ConversationChain`, `ConversationBufferMemory` | Chat with stored history | A message list, or an agent with a checkpointer |
| `RetrievalQA`, `ConversationalRetrievalChain` | Prebuilt RAG chains | An LCEL retrieval chain, or a retriever tool |
| `initialize_agent`, `AgentExecutor` | The old agent runtime | `create_agent` |
| `create_react_agent` from `langgraph.prebuilt` | The previous prebuilt agent | `create_agent` |
| `OpenAI(...)`, `llm.predict(...)` | String-in, string-out completion models | Chat models and `.invoke` |
| "ReAct agent" | An agent that alternated written Thought / Action / Observation text | Native tool calling does the same job with structured requests |
| `from langchain.chains import …`, `from langchain.memory import …` | Old import locations | `langchain-classic`, if you must run old code |

---

# Part 3: what LangChain lacks, and what LangGraph brings

## 23. From chains to graphs

Take stock of `agent.py`. The LangChain parts (messages, model, tools, prompt, the `|` chain) each describe one step. The control flow, the thing that makes it an agent, is twenty lines of hand-written Python: a `for` loop, an `if`, a list. LangChain's composition language has nothing to say about it. That is the gap.

Specifically, Runnables and LCEL do not give you:

1. **Cycles.** A chain is acyclic. "Call the model again until it stops asking for tools" cannot be written with `|`.
2. **Shared state.** A chain passes one value from step to step. There is no common, named state that several steps read and update.
3. **Persistence.** The `messages` list lives in a Python variable. If the process restarts, or the next request lands on another replica, the conversation is gone.
4. **Pause and resume.** You cannot stop mid-run to ask a human "may I delete this pod?", wait an hour for the answer, and continue from that exact point.
5. **Recovery.** If step four of six fails, the only option is to start over, repeating the model calls and tool calls already paid for.
6. **Visibility into the middle.** `invoke` returns at the end. Streaming "now calling list_events" requires threading print statements or callbacks through your loop by hand.
7. **Structured control flow.** Branching to different handlers, running sub-tasks in parallel and joining them, or handing off between agents all end up as ad hoc Python that no tool can inspect, draw or test as a unit.

You can build each of these yourself. LangGraph is what you get when someone builds all of them once, consistently.

### The LangGraph model

A LangGraph program is a **graph** operating on a **state**.

- **State** is a typed dict that every step can read. Each key has a *reducer* saying how updates combine. The usual one, for messages, appends rather than replaces. `MessagesState` is a ready-made state with one `messages` key.
- **Nodes** are plain functions: take the state, return a partial update. A node can call a model, run tools, or do anything else.
- **Edges** say what runs next. A normal edge is fixed. A **conditional edge** is a function that looks at the state and returns the name of the next node, and it is how loops and branches are expressed.
- `START` and `END` mark entry and exit. `compile()` turns the definition into a Runnable.

Here is `agent.py`'s loop as a graph, reusing its `chain`, `TOOLS` and `NAMESPACE`:

```python
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver

def call_model(state: MessagesState):
    reply = chain.invoke({"namespace": NAMESPACE, "messages": state["messages"]})
    return {"messages": [reply]}              # the reducer appends it to state

graph = StateGraph(MessagesState)
graph.add_node("model", call_model)
graph.add_node("tools", ToolNode(TOOLS))      # runs every tool call in the last AIMessage
graph.add_edge(START, "model")
graph.add_conditional_edges("model", tools_condition)   # tool_calls? -> "tools", else -> END
graph.add_edge("tools", "model")              # the cycle LCEL could not express
app = graph.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "session-1"}}
app.invoke({"messages": [("user", "why is the worker failing?")]}, config)
app.invoke({"messages": [("user", "and the reports one?")]}, config)   # same thread: history is loaded for you
```

```text
START ─▶ model ──(tool_calls?)── yes ─▶ tools ─┐
           ▲          │ no                     │
           └──────────┼────────────────────────┘
                      ▼
                     END
```

Everything inside the nodes is still LangChain. LangGraph replaces only the hand-written loop, and `create_agent` (section 18) builds essentially this graph for you.

### What that structure buys

| Gap | LangGraph feature | In practice |
|---|---|---|
| Cycles | Conditional edges, with a `recursion_limit` | Loops are declared and bounded by the runtime, replacing `MAX_STEPS` |
| Shared state | Typed state with reducers | Add keys beyond messages (evidence collected, step count, user scope); nodes update only what they own |
| Persistence | **Checkpointer**: saves state after every step, keyed by `thread_id` | Conversation memory that survives restarts and works across replicas. In-memory for learning; SQLite or Postgres savers for real use |
| Pause and resume | `interrupt()` inside a node; resume with `Command(resume=...)` | Human approval before a risky tool; the run is parked in the checkpoint store, not in a waiting process |
| Recovery | **Durable execution**: resume from the last checkpoint; per-node `RetryPolicy` | A failed step is retried without redoing earlier ones |
| Visibility | **Stream modes**: `updates` (each node's output), `values` (full state), `messages` (model tokens), `custom` | A UI can show tool activity and typed-out answers from one stream |
| Inspection | `get_state`, `get_state_history`, replay or fork from any checkpoint ("time travel") | Debug by rewinding to the step before it went wrong and re-running with a change |
| Parallelism | Several edges out of one node; `Send` for a dynamic number of branches | Check five namespaces at once and merge results through a reducer |
| Composition | **Subgraphs**: a compiled graph used as a node | Multi-agent systems; teams owning separate parts |
| Long-term memory | **Store**: namespaced key-value storage shared across threads | Remember user preferences between conversations |

Two more things worth knowing. A compiled graph can draw itself (`app.get_graph().draw_mermaid()`), so the control flow is documentation. And because control flow is data, not buried in a loop, you can test a single node, or assert which path a given state takes, without calling a model.

### What it costs, and when to skip it

LangGraph adds concepts (state schemas, reducers, checkpoints, threads) and a runtime between you and your code. For a script, a one-shot chain or a learning exercise like this one, a `for` loop is clearer. Persistence in particular brings real obligations: stored conversations are data you must scope, secure and expire.

A reasonable progression:

1. **One model call** with a prompt: plain LangChain, like the Kind chat POC.
2. **A fixed pipeline** (retrieve, then answer): an LCEL chain.
3. **A tool loop** you want to understand: write it by hand once, as here.
4. **A tool loop** you want to ship: `create_agent`, with middleware for limits and approval.
5. **Custom control flow**, persistence, approval steps or several cooperating agents: design the graph yourself in LangGraph.

Vyom's sprint 1 sits at step 5 in shape but deliberately not in scope: it specifies a LangGraph host calling tools on an upstream Kubernetes MCP server, and its rules say not to add persistent graph state yet. So expect the graph and the tool boundary first, and checkpointing later.

### One-paragraph summary

LangChain standardises the pieces: messages, models, prompts, tools, retrievers, and the Runnable interface that lets them compose into straight-line chains. An agent needs a loop around those pieces, and a production agent needs that loop to hold state, survive restarts, pause for people and show its work. LangChain's building blocks do not provide that; LangGraph does, by turning the loop into an explicit graph over saved state. Learn the pieces first, write the loop once by hand, and the graph will read as a formalisation of something you already understand.
