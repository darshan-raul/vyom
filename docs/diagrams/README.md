# Planned architecture diagrams

Updated for the owner-required S1 observability revision on 2026-10-04. These are **planned personal-alpha architecture**, with sprint additions labelled; none proves deployed capability.

- [README deployment architecture — standalone SVG](readme-architecture.svg): cluster/external boundaries, service icons, explicit backend RAG/retrieval labels and five primary connections. Edited directly as SVG, with the canonical logo embedded for portability; separate from the Archify drafts below.
- [Architecture and eight Mermaid views](../ARCHITECTURE.md).
- [Interactive application overview — rendered draft](application.html) and [editable source](application.json).
- [Interactive S1 observability topology — rendered draft](observability.html) and [editable source](observability.json).
- [Observability design and live gates](../OBSERVABILITY.md).
- Direct checker receipts: [application](application.check.json), [observability](observability.check.json).
- Failed atomic delivery receipts: [application](application.delivery.json), [observability](observability.delivery.json).
- [Artifact fingerprints and verification scope](verification.json).

The overview preserves MCP and independent direct-SDK paths and adds an observability branch. The dedicated view expands Prometheus scraping, Alloy node-local logs/OTLP, Loki, Tempo and Grafana queries. Collection/query arrows do not mean application requests depend synchronously on telemetry. Detailed request instrumentation is specified in the design and task gates.

## Current verification status

Both updated sources were rendered through the packaged direct renderer. Each direct artifact checker passed **9/9 showcase checks, 0 composition errors and 0 warnings**, after one layout repair round. Those are structural checks, not visual or runtime acceptance.

The packaged `validate` wrapper could not finish: initial attempts reported child-process `EPERM`, followed by empty checker output/JSON parse failure. Final `deliver` commands exited non-zero with `delivery/receipt-invalid` for both diagrams. The skill was not modified. HTML files are updated direct-rendered drafts, **not atomically accepted Archify deliveries**. Fingerprints record local integrity only.

Browser evidence: **not run**, because successful delivery is a required prerequisite. Perceptual visual review: **not performed**. Mermaid topology and closed fences were reviewed; rendering was not exercised. No runtime observability, model or MCP gates are passed by these checks.

## Reproduce in a capable environment

Use the installed Archify skill path; it is a development tool, not a product dependency. For each `name` (`application`, `observability`), from the repository root:

```sh
node <archify-skill>/bin/archify.mjs validate architecture docs/diagrams/<name>.json --quality showcase --json
node <archify-skill>/bin/archify.mjs deliver architecture docs/diagrams/<name>.json docs/diagrams/<name>.html --quality showcase --json
# Only after successful delivery:
node <archify-skill>/bin/archify.mjs visual-check docs/diagrams/<name>.html --json
```

Inspect both themes and desktop viewport screenshots before recording visual acceptance. Refresh receipts/fingerprints after verification. This optional diagram verification follow-up does not block implementation. Edit JSON and regenerate; do not hand-edit generated HTML.

## README SVG verification

The standalone SVG was parsed as XML and rasterized with installed `rsvg-convert` at its native 1200px width and at 760px README viewing width. Both raster previews were inspected; a label correction removed cramped Kubernetes MCP metadata and gave AWS API metadata more space. This is static SVG visual review, not browser/Archify acceptance or runtime verification. Preview PNGs are temporary files under `/tmp`; README embeds the editable SVG directly.
