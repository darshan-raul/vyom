export type Resource = { id: string; uid: string; kind: "Pod" | "Deployment"; name: string; phase?: string; ready: number; containers?: number; restarts?: number; reasons?: string[]; desired?: number; available?: number }
export type Evidence = { cluster: string; namespace: string; collected_at: string; sources: { kind: string; coverage: "complete" | "partial" | "unavailable"; resources: Resource[]; error: string | null }[] }
export type ChatResult = { status: "ok" | "partial" | "unavailable"; answer: string; evidence: Evidence | null }
export type Message = { role: "user" | "assistant"; content: string }
export type Health = { cluster: string; namespace: string; model: string; read_only: boolean }

export async function getHealth(): Promise<Health> {
  const response = await fetch("/api/health", { signal: AbortSignal.timeout(5000) })
  if (!response.ok) throw new Error("Backend configuration is unavailable.")
  return response.json()
}
export async function ask(question: string, history: Message[], signal: AbortSignal): Promise<ChatResult> {
  const response = await fetch("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" }, signal,
    body: JSON.stringify({ question, history: history.slice(-4).map(m => ({ ...m, content: m.content.slice(0, 2000) })) }),
  })
  if (response.status === 429) throw new Error("The backend is busy. Try again shortly.")
  if (!response.ok) throw new Error(response.status === 422 ? "Keep questions under 2,000 characters." : "The request failed. Check the backend and try again.")
  return response.json()
}
