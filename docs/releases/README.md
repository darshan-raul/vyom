# Release Evidence Template

Copy this template to `YYYY-MM-DD-<environment>-<revision>.md` for each release decision. Do not commit secrets, raw tenant payloads, AWS resource identifiers, prompts, or responses.

```markdown
# Release: <environment> / <revision>

- Date/time (UTC):
- Environment: Kind | EKS
- Git revision:
- Immutable image digests:
- Owner approval (EKS/live only):
- Scope:

## Gate results

| Gate | Commands/tests | Result | Redacted evidence summary |
|---|---|---|---|
| A — Kind | | pass / fail / n/a | |
| B — EKS | | pass / fail / n/a | |
| C — simulated AWS | | pass / fail / n/a | |
| D — live personal AWS | | pass / fail / n/a | |

## Deployment / rollback

- EKS deployment revision:
- Previous revision/digests:
- Rollback commands and resulting revision (if used):

## Decision

- Owner decision: pass | fail and rolled back | not applicable to this milestone
- Follow-up tracker items:
```
