# Architecture diagrams and verification

Updated for the owner-approved MCP host/client architecture revision on 2026-10-03. All diagrams describe the **planned end-of-S6 personal alpha**. None is evidence of a deployed product.

- [Detailed architecture and seven Mermaid diagrams](../ARCHITECTURE.md).
- [Interactive application overview — rendered draft](application.html).
- [Editable Archify source](application.json).
- [Direct artifact check receipt](application.check.json).
- [Failed atomic delivery receipt](application.delivery.json).
- [File fingerprints and verification scope](verification.json).

## Current verification status

The direct Archify renderer produced the HTML. The direct artifact checker passed all **9 showcase checks, 0 composition errors, 0 warnings**. Two layout correction rounds addressed label placement and desktop readability for the revised host/client diagram. The source and rendered HTML now both show upstream MCP integrations and the separate direct-SDK path.

The normal `validate`/`deliver` wrapper could not complete in this environment: initial child-process attempts reported `EPERM`; later attempts failed to parse empty child-process checker output (`delivery/receipt-invalid`). The skill was not modified. The saved HTML is direct-rendered output, **not an atomically accepted Archify delivery**. SHA-256 fingerprints are local integrity records, not successful delivery receipts.

Browser evidence: **not run**, because the required successful delivery prerequisite was not met. Perceptual visual review: **not performed**. Mermaid source was reviewed for architecture consistency and closed code fences; Mermaid rendering was not exercised. Do not claim full visual acceptance from the structural check.

## Reproduce in a capable environment

Use your installed Archify skill path; it is a development tool, not a product dependency. From the repo root:

```sh
node <archify-skill>/bin/archify.mjs validate architecture docs/diagrams/application.json --quality showcase --json
node <archify-skill>/bin/archify.mjs deliver architecture docs/diagrams/application.json docs/diagrams/application.html --quality showcase --json
# Only after successful delivery:
node <archify-skill>/bin/archify.mjs visual-check docs/diagrams/application.html --json
```

Inspect both themes and required desktop viewport screenshots before recording perceptual acceptance. Update receipts/fingerprints after successful verification. This is an optional, untracked follow-up; it does not block any task. Do not hand-edit generated HTML: change JSON, validate, then regenerate.
