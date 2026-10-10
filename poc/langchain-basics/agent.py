"""LangChain fundamentals: a terminal chat that answers questions about one
Kubernetes namespace by calling three read-only tools.

Read this top to bottom alongside CONCEPTS.md. The numbered sections match
the numbered concepts there.
"""
import os
import sys

import urllib3
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# The namespace is fixed here, by us. The model is never asked which namespace
# to look at, so nothing it says (or is tricked into saying) can widen the scope.
NAMESPACE = "shop"
MODEL = os.environ.get("MODEL_NAME", "anthropic/claude-haiku-5.5")
MAX_STEPS = 6  # upper bound on model calls per question, so a confused model cannot loop forever


# --- 0. Plain Kubernetes client: no LangChain yet ----------------------------
# load_kube_config reads a kubeconfig file exactly like kubectl does: server
# address, CA certificate and the ServiceAccount token from the README steps.
config.load_kube_config(config_file=os.environ.get("KUBECONFIG_PATH", ".private/kubeconfig"))
core = client.CoreV1Api()

# ApiException: the API server answered with an error (401 expired token, 403 not
# allowed by RBAC, 404 no such pod). HTTPError: it could not be reached at all.
K8S_ERRORS = (ApiException, urllib3.exceptions.HTTPError)


def k8s_error(exc) -> str:
    if isinstance(exc, ApiException):
        return f"error: Kubernetes API returned {exc.status} {exc.reason}"
    return "error: could not connect to the Kubernetes API server"


# --- 1. Tools ----------------------------------------------------------------
# @tool turns an ordinary function into a LangChain tool. Three things are
# taken from the function and sent to the model:
#   - its name            -> the tool name
#   - its type hints      -> a JSON schema for the arguments
#   - its docstring       -> the description the model reads to decide WHEN to call it
# The docstring is therefore prompt text, not just documentation. Write it for the model.
#
# Tools return strings. Whatever a tool returns is what the model sees, so
# errors are returned as text too: the model can then tell you what went wrong.

@tool
def list_pods() -> str:
    """List every pod in the namespace with its phase, ready containers and restart count.
    Call this first to see what exists and which pods look unhealthy."""
    try:
        pods = core.list_namespaced_pod(NAMESPACE, limit=50).items
    except K8S_ERRORS as exc:
        return k8s_error(exc)
    if not pods:
        return f"No pods in namespace {NAMESPACE}."
    lines = []
    for pod in pods:
        statuses = pod.status.container_statuses or []
        ready = sum(1 for s in statuses if s.ready)
        restarts = sum(s.restart_count for s in statuses)
        lines.append(f"{pod.metadata.name}  phase={pod.status.phase}  ready={ready}/{len(pod.spec.containers)}  restarts={restarts}")
    return "\n".join(lines)


@tool
def get_pod_details(pod_name: str) -> str:
    """Show one pod's containers: image, current state, the reason it is waiting or
    terminated, exit code and restart count. Use the exact pod name from list_pods."""
    try:
        pod = core.read_namespaced_pod(pod_name, NAMESPACE)
    except K8S_ERRORS as exc:
        return k8s_error(exc)
    lines = [f"pod={pod.metadata.name}  phase={pod.status.phase}  node={pod.spec.node_name}"]
    for s in pod.status.container_statuses or []:
        if s.state.running:
            state = "running"
        elif s.state.waiting:
            state = f"waiting reason={s.state.waiting.reason}"
        else:
            state = f"terminated reason={s.state.terminated.reason} exit_code={s.state.terminated.exit_code}"
        line = f"container={s.name}  image={s.image}  state={state}  restarts={s.restart_count}"
        # The previous run is what explains a crash loop: the current state is just "waiting".
        if s.last_state and s.last_state.terminated:
            line += f"  last_exit_code={s.last_state.terminated.exit_code}  last_reason={s.last_state.terminated.reason}"
        lines.append(line)
    return "\n".join(lines)


@tool
def list_events(pod_name: str = "") -> str:
    """List recent Kubernetes events (scheduling, image pulls, back-offs, failures).
    Pass pod_name to see only that pod's events, or leave it empty for the whole namespace."""
    try:
        # field_selector filters on the server, the same as `kubectl get events --field-selector ...`.
        selector = f"involvedObject.name={pod_name}" if pod_name else None
        events = core.list_namespaced_event(NAMESPACE, field_selector=selector, limit=100).items
    except K8S_ERRORS as exc:
        return k8s_error(exc)
    if not events:
        return "No events found."
    events.sort(key=lambda e: (e.last_timestamp or e.event_time or e.metadata.creation_timestamp))
    # Bound what goes back to the model: last 15 events, messages cut to 200 characters.
    # Tool output lands in the model's context and you pay for every token of it.
    return "\n".join(
        f"{e.type}  {e.reason}  {e.involved_object.kind}/{e.involved_object.name}  x{e.count or 1}  {(e.message or '')[:200]}"
        for e in events[-15:]
    )


TOOLS = [list_pods, get_pod_details, list_events]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


# --- 2. Chat model -----------------------------------------------------------
# ChatOpenAI speaks the OpenAI Chat Completions wire format. OpenRouter exposes
# that same format for many providers, so pointing base_url at OpenRouter is all
# it takes to use a Claude model through this class.
if not os.environ.get("OPENROUTER_API_KEY"):
    sys.exit("Set OPENROUTER_API_KEY first (see README step 4).")

model = ChatOpenAI(
    model=MODEL,
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    temperature=0,   # we want the same diagnosis each time, not creative variation
    max_tokens=800,
    timeout=60,
)

# --- 3. bind_tools -----------------------------------------------------------
# bind_tools does NOT give the model the ability to run anything. It returns a
# new model object that attaches the three tool schemas to every request. All
# the model can do with them is reply "I would like list_pods called" instead
# of replying with text. Running the function is our job, in section 6.

model_with_tools = model.bind_tools(TOOLS)

# --- 4. Prompt template ------------------------------------------------------
# A template is a reusable message list with holes in it. {namespace} is filled
# with a string; MessagesPlaceholder is filled with a whole list of messages
# (the conversation so far), which is how the model gets memory.

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a read-only Kubernetes assistant for the namespace '{namespace}'. "
     "Use the tools to look at the cluster before answering; never guess at state you have not observed. "
     "Name the pods you are talking about and say which observation supports each conclusion. "
     "You cannot change anything. If asked to, say so."),
    MessagesPlaceholder("messages"),
])

# --- 5. Chain (LCEL) ---------------------------------------------------------
# The | operator pipes one step's output into the next. Calling
# chain.invoke({...}) fills the template, then sends the resulting messages to
# the model. Both objects are "Runnables": they share invoke/stream/batch.
chain = prompt | model_with_tools


# --- 6. The agent loop -------------------------------------------------------
# An "agent" is this loop and nothing more:
#   ask the model -> if it requested tools, run them and append the results -> ask again
# until the model replies with plain text.

def answer(messages: list) -> AIMessage:
    """Run the loop for the latest question. Appends every new message to `messages`."""
    
    for _ in range(MAX_STEPS):
        reply: AIMessage = chain.invoke({"namespace": NAMESPACE, "messages": messages})
        # The reply must go into history even when it only contains tool requests:
        # each ToolMessage below refers back to it by tool_call_id.
        messages.append(reply)

        if not reply.tool_calls:
            return reply  # plain text: the model is done

        # A single reply may request several tools at once.
        for call in reply.tool_calls:
            # call is a dict: {"name": "get_pod_details", "args": {"pod_name": "..."}, "id": "..."}
            print(f"  [tool] {call['name']}({call['args']})")
            selected = TOOLS_BY_NAME.get(call["name"])
            if selected is None:
                # Models occasionally invent a tool name. Tell it, rather than crash.
                result = ToolMessage(content=f"error: unknown tool {call['name']}", tool_call_id=call["id"])
            else:
                # Passing the whole call dict makes invoke() validate the arguments
                # against the schema, run the function and wrap the returned string
                # in a ToolMessage carrying the matching tool_call_id.
                result = selected.invoke(call)
            messages.append(result)

    return AIMessage(content=f"Stopped after {MAX_STEPS} model calls without a final answer.")


# --- 7. Conversation ---------------------------------------------------------
# The model is stateless: every request must carry the whole conversation.
# This one list IS the memory. It lives in this process and is gone when you exit.
def main():
    messages = []
    print(f"Asking {MODEL} about namespace '{NAMESPACE}'. Empty line or Ctrl-D to quit.")
    while True:
        try:
            question = input("\nyou> ").strip()
        except EOFError:
            break
        if not question:
            break
        messages.append(HumanMessage(content=question))
        reply = answer(messages)
        print(f"\nassistant> {reply.text}")

        # What the provider billed for this last model call. Input tokens grow
        # with every turn because the full history is resent.
        if reply.usage_metadata:
            print(f"  [tokens] in={reply.usage_metadata['input_tokens']} out={reply.usage_metadata['output_tokens']}  history={len(messages)} messages")


if __name__ == "__main__":
    main()
