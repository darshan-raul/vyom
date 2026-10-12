import { useEffect, useRef, useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ask, getHealth, type ChatResult, type Health, type Message } from "@/lib/api"

const suggestions = ["Which pods are unhealthy?", "Summarize deployment readiness.", "Which pods have restarted?"]

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState<ChatResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const controller = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => { let mounted = true; getHealth().then(h => { if (mounted) setHealth(h) }).catch(() => { if (mounted) setError("Backend unavailable. Check the API workload and Secret configuration.") }); return () => { mounted = false; controller.current?.abort() } }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }) }, [messages, busy])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const prompt = question.trim()
    if (!prompt || busy) return
    setBusy(true); setError(""); setQuestion(""); setResult(null)
    const previous = messages
    setMessages([...previous, { role: "user", content: prompt }])
    const abort = new AbortController(); controller.current = abort
    const timer = window.setTimeout(() => abort.abort(), 65000)
    try {
      const response = await ask(prompt, previous, abort.signal)
      setResult(response)
      setMessages([...previous, { role: "user", content: prompt }, { role: "assistant", content: response.answer }])
      if (response.status === "unavailable") setError("Answer unavailable. Review the response and evidence coverage below.")
    } catch (failure) {
      setError(failure instanceof DOMException && failure.name === "AbortError" ? "Request stopped or timed out. The backend has its own 60-second limit." : failure instanceof Error ? failure.message : "Unable to send question.")
      setMessages(previous); setQuestion(prompt)
    } finally { window.clearTimeout(timer); setBusy(false); controller.current = null }
  }

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><img src="/vyom-logo.png" width="44" height="42" alt="Vyom logo" /><div><strong>Vyom</strong><span>Kind chat / separate POC</span></div></div><span className="status-tag">Read-only</span></header>
    <main>
      <div className="page-heading"><p className="eyebrow">A question, a fresh snapshot, an answer.</p><h1>Your cluster, in conversation.</h1><p>Inspect pods and deployments in one target namespace.</p></div>
      <div className="workspace">
        <section className="chat-panel" aria-labelledby="chat-title">
          <div className="panel-heading"><h2 id="chat-title">Chat</h2><Button variant="ghost" size="sm" disabled={busy || !messages.length} onClick={() => { setMessages([]); setResult(null); setError("") }}>Clear</Button></div>
          <div className="transcript" role="log" aria-live="polite" aria-busy={busy}>
            {!messages.length && <div className="empty-chat"><span className="eyebrow">Start an investigation</span><h3>What would you like to know?</h3><p>Each question collects fresh evidence. Answers can explain status and suggest checks; this POC cannot execute changes.</p><div className="suggestions">{suggestions.map(text => <Button key={text} variant="outline" onClick={() => setQuestion(text)}>{text}</Button>)}</div></div>}
            {messages.map((message, index) => <article className={`message ${message.role}`} key={index}><span className="eyebrow">{message.role === "user" ? "You" : "Vyom"}</span><p>{message.content}</p></article>)}
            {busy && <div className="pending">Reading target evidence and asking the model…</div>}<div ref={bottom} />
          </div>
          <form onSubmit={submit} className="composer"><label htmlFor="question" className="sr-only">Question about the target namespace</label><Textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about workload health…" maxLength={2000} disabled={busy} /><div className="composer-footer"><span>Scope is configured on the server.</span>{busy ? <Button type="button" variant="outline" onClick={() => controller.current?.abort()}>Stop waiting</Button> : <Button type="submit" disabled={!question.trim()}>Ask Vyom</Button>}</div></form>
          {error && <p role="alert" className="error-banner">{error}</p>}
        </section>
        <aside className="evidence-panel" aria-labelledby="evidence-title">
          <div className="panel-heading"><h2 id="evidence-title">Target &amp; evidence</h2></div>
          <dl className="connection"><dt>Cluster</dt><dd>{health?.cluster ?? "Awaiting API"}</dd><dt>Namespace</dt><dd>{health?.namespace ?? "—"}</dd><dt>Model</dt><dd>{health?.model ?? "—"}</dd></dl>
          <p className="scope-note">Pod status and deployment readiness only. No logs, Secrets, exec or writes.</p>
          {!result?.evidence && <div className="empty-evidence">Ask a question to inspect its collected evidence.</div>}
          {result?.evidence && <><p className="collected">Collected {new Date(result.evidence.collected_at).toLocaleTimeString()}</p>{result.evidence.sources.map(source => <section className="source" key={source.kind}><div className="source-heading"><h3>{source.kind}s</h3><span className={`coverage ${source.coverage}`}>{source.coverage}</span></div>{source.error && <p className="source-error">{source.error}</p>}{!source.resources.length && <p className="empty-evidence">{source.coverage === "complete" ? "No resources in this namespace." : "No resources collected; source is unavailable or incomplete."}</p>}{source.resources.map(resource => <div className="resource" key={resource.id}><strong>{resource.name}</strong><span>{resource.kind === "Pod" ? `${resource.phase} · ${resource.ready}/${resource.containers} ready · ${resource.restarts} restarts` : `${resource.ready}/${resource.desired} ready · ${resource.available} available`}</span>{!!resource.reasons?.length && <small>{resource.reasons.join(", ")}</small>}</div>)}</section>)}<details className="raw-evidence"><summary>Sanitized evidence JSON</summary><pre>{JSON.stringify(result.evidence, null, 2)}</pre></details></>}
        </aside>
      </div>
      <footer>Local POC · browser-only conversation · no RAG or MCP</footer>
    </main>
  </div>
}
