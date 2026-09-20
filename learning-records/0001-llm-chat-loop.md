# 0001 — LLM chat loop

## Learned

An LLM chat UI is a loop: user message → authenticated backend → tenant-scoped retrieval → model response or structured tool call → server-side tool execution → grounded streamed answer.

## Durable insight

The model is not the source of truth or the authorization boundary. The application supplies context and enforces policy; tools supply current facts.

## Evidence

- Completed Lesson 1: `lessons/0001-llm-as-chat-ui.html`
- Reviewed Transformer paper and AI SDK tool-calling documentation in `RESOURCES.md`.

## Next edge

Learn tokens and context windows, then map the loop onto a concrete Cloud Compass SSE endpoint.
