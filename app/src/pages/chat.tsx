import { useChat } from "ai/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send } from "lucide-react";
import { agentClient } from "@/lib/api";
import { useEffect, useRef } from "react";

export function ChatPage() {
  const { messages, input, handleInputChange, handleSubmit, isLoading, error, setMessages } = useChat({
    api: "/api/agent/chat",
    headers: async () => {
      const token = sessionStorage.getItem("kc_token") ?? "";
      return {
        Authorization: token ? `Bearer ${token}` : "",
        "X-Tenant-Id": sessionStorage.getItem("kc_sub") ?? "",
      };
    },
    streamProtocol: "data",
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    agentClient.get("/agent/whoami").then(() => undefined).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-4 h-[calc(100vh-3rem)] flex flex-col">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Vyom Assistant</h1>
        <p className="text-sm text-muted-foreground">
          Ask about cost, security, inventory, FinOps, SCA, or compliance — answers cite the tools and KB chunks used.
        </p>
      </div>

      <Card className="flex-1 flex flex-col">
        <CardHeader>
          <CardTitle>Conversation</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col gap-3">
          <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-2">
            {messages.length === 0 && (
              <div className="text-sm text-muted-foreground">
                Try: <em>"What did we spend on EC2 last month?"</em>
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                className={
                  m.role === "user"
                    ? "ml-auto max-w-[80%] rounded-md bg-primary text-primary-foreground px-3 py-2 text-sm"
                    : "mr-auto max-w-[80%] rounded-md bg-muted px-3 py-2 text-sm"
                }
              >
                <div className="whitespace-pre-wrap">{m.content}</div>
                {m.toolInvocations && m.toolInvocations.length > 0 && (
                  <details className="mt-2 text-xs opacity-80">
                    <summary>Tool calls ({m.toolInvocations.length})</summary>
                    <pre className="mt-1 overflow-x-auto">
                      {JSON.stringify(m.toolInvocations, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
            {error && (
              <div className="text-sm text-destructive">Error: {error.message}</div>
            )}
          </div>
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={handleInputChange}
              placeholder="Ask Vyom…"
              disabled={isLoading}
            />
            <Button type="submit" disabled={isLoading}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
