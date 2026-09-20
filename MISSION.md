# Mission: LLM-powered chat for Cloud Compass

## Why
Learn enough about large language models to design and ship a trustworthy chat experience for Cloud Compass users. The chat should explain cloud spend and operations in plain language, use tenant-scoped live data, and remain read-only and auditable.

## Success looks like
- Explain the request → context → model → tool → cited answer loop.
- Design a chat endpoint that streams responses while enforcing tenant and role boundaries.
- Distinguish model knowledge from retrieved cloud facts and identify when an answer needs a tool call.

## Constraints
- Short, practical lessons tied to the existing Cloud Compass architecture.
- Prefer managed model APIs and read-only cloud tools; no tenant document uploads in the beta.

## Out of scope
- Training a foundation model from scratch.
- Deep calculus or GPU-kernel optimization for now.
