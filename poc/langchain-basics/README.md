# LangChain basics: chat with a Kind cluster from your terminal

A learning exercise, separate from the Vyom plan and from `poc/kind-chat/`. One Python file runs on your machine, talks to a model through OpenRouter and answers questions about four pods in a local Kind cluster using three read-only tools.

- [`agent.py`](agent.py): the whole app, commented section by section.
- [`CONCEPTS.md`](CONCEPTS.md): the LangChain ideas behind each section. Read it with the code open.
- [`workloads.yaml`](workloads.yaml): the namespace, four pods and the read-only identity.

Run everything from `poc/langchain-basics/`.

## 1. Create the cluster and workloads

```sh
kind create cluster --name lc-basics
kubectl --context kind-lc-basics apply -f workloads.yaml
kubectl --context kind-lc-basics -n shop get pods --watch
```

Wait about a minute, then Ctrl-C. You should see two healthy pods and two broken ones:

| Pod | Expected state | Why |
|---|---|---|
| `web-…` | `Running` 1/1 | nginx |
| `api-…` | `Running` 1/1 | a process that sleeps |
| `worker-…` | `CrashLoopBackOff`, restarts climbing | exits with code 1 after 5 seconds |
| `reports-…` | `ErrImagePull` / `ImagePullBackOff` | image tag does not exist |

## 2. Build a kubeconfig for the app

`kind create cluster` already put an admin context (`kind-lc-basics`) in `~/.kube/config`. The app does not use it. It gets its own kubeconfig holding a token for the `agent-reader` ServiceAccount, which may only read pods and events in `shop`.

A kubeconfig is three things: where the cluster is, how to trust it (CA certificate) and who you are (here, a token).

```sh
umask 077
mkdir -p .private

# Where: the API server address Kind published on localhost.
SERVER=$(kubectl config view --context kind-lc-basics --minify \
  -o jsonpath='{.clusters[0].cluster.server}')

# Trust: the cluster's CA certificate.
kubectl config view --context kind-lc-basics --minify --raw \
  -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' \
  | base64 --decode > .private/ca.crt

# Who: a short-lived token for the read-only ServiceAccount.
TOKEN=$(kubectl --context kind-lc-basics -n shop create token agent-reader --duration=8h)

# Assemble the three into a standalone file.
KC=.private/kubeconfig
kubectl config --kubeconfig $KC set-cluster lc-basics --server="$SERVER" \
  --certificate-authority=.private/ca.crt --embed-certs=true
kubectl config --kubeconfig $KC set-credentials agent-reader --token="$TOKEN"
kubectl config --kubeconfig $KC set-context agent --cluster=lc-basics \
  --user=agent-reader --namespace=shop
kubectl config --kubeconfig $KC use-context agent
```

Check that this identity can read and cannot do anything else:

```sh
kubectl --kubeconfig .private/kubeconfig get pods            # works
kubectl --kubeconfig .private/kubeconfig get events | tail -5  # works
kubectl --kubeconfig .private/kubeconfig get secrets         # Forbidden
kubectl --kubeconfig .private/kubeconfig delete pod --all    # Forbidden
```

`.private/` is ignored by Git. When the token expires the tools start returning `401 Unauthorized`: rerun the `TOKEN=` and `set-credentials` lines.

## 3. Install the Python dependencies

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Three packages: `langchain-core` (messages, prompts, tools, the `|` operator), `langchain-openai` (the chat model class) and `kubernetes` (the official Python client).

## 4. Give it your OpenRouter key and run

```sh
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY   # paste the key, press Enter; nothing is echoed
.venv/bin/python agent.py
```

The key lives only in this shell's environment. To use another model: `MODEL_NAME=<openrouter model id> .venv/bin/python agent.py`. It must support tool calling.

## 5. Ask things, and watch the tool calls

Every tool the model requests is printed as a `[tool]` line before the answer. That is the part to watch.

| Ask | What to notice |
|---|---|
| `what is running here?` | One `list_pods` call, then an answer |
| `why is the worker failing?` | It chains tools: `list_pods` to find the full pod name, then `get_pod_details` and/or `list_events` |
| `and the reports one?` | A follow-up only makes sense with history; watch `in=` tokens grow each turn |
| `what is 2 + 2?` | No tool call: the model decides whether tools are needed |
| `delete the worker pod` | It refuses: no such tool exists, and the token could not do it anyway |
| `show me the logs of worker` | It has no log tool; it should say so rather than invent output |

Then change something in a second terminal and ask again. Each question triggers fresh tool calls, so the answer follows the cluster:

```sh
kubectl --context kind-lc-basics -n shop set image deployment/reports reports=nginx:1.28-alpine
kubectl --context kind-lc-basics -n shop scale deployment/web --replicas=3
```

## Experiments in the code

Small edits to `agent.py` that each teach one thing. `CONCEPTS.md` explains what you will see.

1. Change `model_with_tools` to plain `model` in the `chain = ...` line. The model can no longer look at the cluster and has to say so (or guess).
2. Replace the `list_pods` docstring with `"""Does stuff."""`. The model gets worse at choosing it: the docstring is the prompt.
3. Set `MAX_STEPS = 1` and ask why the worker is failing. The loop stops before the model can use what the tool returned.
4. Add `print(messages)` at the end of `answer()` to see the full message list that makes up one turn.
5. Write a fourth tool, for example `list_deployments()` using `client.AppsV1Api()`. You will also need to add `deployments` under the `apps` API group in the Role in `workloads.yaml` and re-apply it; until you do, the tool returns `403 Forbidden` and the model reports that.

## Clean up

```sh
kind delete cluster --name lc-basics
rm -rf .private .venv
unset OPENROUTER_API_KEY
```
