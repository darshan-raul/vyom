> Continuous operations: Overview is an operations desk with active issues, changes, freshness and investigation progress; issue detail supports evidence, history and conversational follow-up. See [accepted design](../CONTINUOUS_OPERATIONS.md). Add surfaces only with working data; retain existing visual tokens.

> Aligned with the 2026-10-29 rescope ([snapshot](../RESCOPE_AUDIT.md)): §0 is the surface schedule. Mockups keep their original spend, compliance and runbook content as visual reference only; do not implement it.

# Vyom — Frontend Design Spec

> Source of truth for how Vyom's UI looks. Owner-supplied on 12 October 2026 and adapted here to
> the [constitution](../../CONSTITUTION.md): what Vyom shows, and when, follows the
> active roadmap (§0). Reference mockups live in [mockups/](mockups/) (`*.dc.html`). They are
> design-tool source (HTML markup + inline styles + a small logic class), not runnable pages; read
> them for exact layout, values and sample copy. When this spec and a mockup disagree, this spec
> wins. When this spec and the constitution disagree on scope, the constitution wins.
> Stack: React + Refine + shadcn/ui + Tailwind.
> Logo in the app: [vyom-logo.png](vyom-logo.png), the circular transparent mark; see
> [branding](../BRANDING.md).

---

## 0. Scope and rollout

[Active roadmap](../IMPLEMENTATION_PLAN.md) determines delivery. Mockups are visual references, not requirements. Use real data or explicit unavailable/empty states; never sample numbers.

| Surface | Gate | Content |
|---|---|---|
| Inventory and resource detail | R3 | Scoped lists, ownership, health, evidence and freshness |
| Investigation | R4 | Workload skill, bounded steps, evidence and supported conclusions |
| Operations overview and issue detail | R4a | Changes, issues, episodes, job progress, natural-language follow-up and recovery |
| Security | R5/R8 | Deterministic findings, categories, evidence, policy and remediation |
| AWS/cross-platform | R6–R9 | Scoped AWS resources, connectivity and verified relationships |
| Identity | R10 | Verified membership/current grants before exposure |

Spend, savings, forecasts, Terraform drafting, CVE/SBOM and generic compliance mockup content are excluded. Runbooks are deferred. Do not build these surfaces or disabled navigation promises. Existing tokens and reusable visual patterns below remain the look; domain examples outside this table have no scope authority.

Evidence may be zero, partial, stale, denied or missing; these remain distinct. A missing source never implies healthy resources. Display observed time and collection coverage, not a fabricated current state.

---

## 1. Principles

1. **Mission-control console, not a SaaS template.** Dark navy, hairline borders, monospace labels. Calm by default; colour only where something needs attention.
2. **Colour = state, never decoration.** Status colours (alert / caution / nominal) appear only on things with that status. Healthy resources are quiet blue, not green.
3. **The agent is a first-class surface.** Sky blue (`--vy-agent`) belongs to Vyom's agent: the Ask panel, investigation steps and citations. Don't use it for anything else.
4. **Show change, not just state.** Prefer "what changed since X" (diffs, before/after, deltas) over static totals. A finding should say *what changed and when it was observed*; show an actor only when evidence supports it.
5. **Every claim is traceable.** Agent answers and evidence carry citations to the API call or stored evidence they came from (`ec2:DescribeSecurityGroups`, `k8s pods_list`).
6. **Read-only is visible.** Primary actions are *ask* / *open evidence* / *acknowledge*, never *remediate*. Vyom reads; it does not change a cluster or an account, and it does not draft changes in this roadmap.
7. **No fake data in production UI.** Missing values render as an explicit empty state, not a placeholder number.

---

## 2. Design tokens

Define once as CSS variables in `frontend/src/index.css`; map them to shadcn's variable names so shadcn components inherit the theme. Vyom is **dark-only** for now.

### 2.1 Colour

```css
:root {
  /* Surfaces (logo night-sky navy) */
  --vy-bg:          #050C1F;  /* page */
  --vy-surface-1:   #061230;  /* inset / code / diff wells */
  --vy-surface-2:   #0A1633;  /* cards, panels */
  --vy-surface-3:   #0C1A3A;  /* raised: inputs, list rows, secondary buttons */
  --vy-surface-sel: #1A2C55;  /* selected tab / row */

  /* Lines */
  --vy-line-faint:  #16264A;  /* row dividers */
  --vy-line:        #1C2F57;  /* card borders */
  --vy-line-strong: #27406F;  /* button borders, chips */

  /* Text */
  --vy-text:        #EAF1FF;  /* primary */
  --vy-text-2:      #BCC9E3;  /* secondary / body on dark */
  --vy-text-3:      #93A4C8;  /* labels, captions */
  --vy-text-4:      #7083AB;  /* hints, timestamps */

  /* Brand + agent (logo sky blue) */
  --vy-agent:       #6CB4FF;  /* agent surfaces, links, citations */
  --vy-agent-ink:   #04122E;  /* text on --vy-agent fills */
  --vy-agent-line:  #2A4A85;  /* agent-panel borders */
  --vy-agent-bg:    #0B1D42;  /* agent-panel fill (gradient to #081633) */
  --vy-royal:       #1E4FB8;  /* deep accent for gradients / highlights */

  /* Status */
  --vy-alert:       #FF6F5E;  /* exposed, critical, riskier */
  --vy-caution:     #F5B84A;  /* unhealthy state or configuration caution */
  --vy-ok:          #4FD1A5;  /* nominal telemetry, safer, improvements */
  --vy-quiet:       #4C6FB0;  /* healthy/nominal resources in charts (NOT green) */
  --vy-quiet-2:     #2B4A88;  /* healthy fills, inactive bars */

  /* shadcn mapping */
  --background: var(--vy-bg);
  --foreground: var(--vy-text);
  --card: var(--vy-surface-2);
  --card-foreground: var(--vy-text);
  --popover: var(--vy-surface-3);
  --popover-foreground: var(--vy-text);
  --primary: var(--vy-text);            /* primary button = light fill, navy text */
  --primary-foreground: var(--vy-bg);
  --secondary: var(--vy-surface-3);
  --secondary-foreground: var(--vy-text);
  --muted: var(--vy-surface-3);
  --muted-foreground: var(--vy-text-3);
  --accent: var(--vy-surface-sel);
  --accent-foreground: var(--vy-text);
  --destructive: var(--vy-alert);
  --border: var(--vy-line);
  --input: var(--vy-line);
  --ring: var(--vy-agent);
  --radius: 8px;
}
```

**Status tint recipe** (for badges, row backgrounds, rings): the text is the status colour, the border is that colour at about 35–40% alpha, and the fill is that colour at 6–12% alpha. Example for alert: text `#FF6F5E`, border `rgba(255,111,94,.35)`, bg `rgba(255,111,94,.08)`.

**Semantic rule for change:** colour a change by its **effect**, not its sign. "−9 exposed" is green (safer); "+14 drift" is red/amber (riskier); "+27 nominal" is green.

### 2.2 Page background

```css
body {
  background-color: var(--vy-bg);
  background-image:
    radial-gradient(ellipse 80% 50% at 70% -10%, rgba(30,79,184,.35), transparent 70%),
    radial-gradient(ellipse 60% 40% at 0% 100%, rgba(76,155,242,.10), transparent 70%);
}
```

No grid: the owner removed the mockups' 32px grid lines on 12 October 2026. The mockups still show it.

### 2.3 Typography

| Role | Font | Size / weight | Notes |
|---|---|---|---|
| Display (greeting, hero numbers) | Archivo | 44–64px / 600, tracking −0.02 to −0.04em | `line-height: 1–1.05` |
| Section title | Archivo | 15–18px / 500–600 | |
| Body | Archivo | 14–16px / 400, line-height 1.55 | `--vy-text-2` on dark |
| **Section label** | JetBrains Mono | 11px / 400, **UPPERCASE, tracking 0.16em** | `--vy-text-3`. Numbered: `01 / POSTURE`, `01.1 / WHAT MOVES THE SCORE` |
| Micro label / badge | JetBrains Mono | 9–10px, uppercase, tracking 0.1–0.14em | |
| Identifiers (ARNs, paths, API calls, times) | JetBrains Mono | 11–12px | always mono: `rds:[prod-billing-db]`, `T−3h` |

Load with `@fontsource-variable/archivo` and `@fontsource-variable/jetbrains-mono` (bundled, no font CDN). **Don't use Inter, Roboto or system UI as the visible face.**

### 2.4 Spacing, radius, elevation

- Spacing scale: 4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32. Panel padding is 20–24px; the gap between panels is 20px.
- Radius: 4 (badges, mono tags), 6 (buttons, inputs), 8–10 (cards), 12 (metric cards), 999 (pills, chips, segmented tabs).
- Borders do the work; no drop shadows on cards. Glow (`box-shadow: 0 0 Npx <colour>`) is reserved for **live/changed/alert** things: status dots, changed marks, the agent panel, the blast-radius core.
- Touch targets ≥ 44px for buttons; compact controls (tabs, chips) ≥ 32px.

---

## 3. Layout

- App shell: **sidebar (220–256px) + main**, laid out as a `flex-wrap` row. Main is `flex: 999 1 560px; min-width: 0`, so the sidebar stacks above it on narrow screens. The sidebar is never sticky or `100vh`.
- Main content max width is about 1360–1440px, centred.
- Two-column body: findings `flex: 2 1 560px` and a right rail `flex: 1 1 320px`.
- Wide tables go inside an `overflow-x: auto` box.
- Header ticker (top of main): mono 11px status counts plus a timestamp, with a hairline under it. On Today it carries the API and agent state; on Kubernetes it counts pods by state (`● 1 NOMINAL  ▲ 0 CAUTION  ■ 1 ALERT`); nodes and instances only when their real inventory is available.

### Sidebar
- Logo (circular image, 40–44px, faint blue halo) + `VYOM` wordmark (19px/700, tracking 0.22em) + mono sub-label `AWS · K8S · ALPHA`.
- Scope card (account, region, cluster, namespace) once the API serves the trusted context; it becomes a switcher only with verified membership in R10. Search (with a `⌘K` hint) arrives with something to search.
- Nav groups contain only implemented surfaces: Overview, Inventory, Investigations and Security as their gates land. Active item: **2px amber left border** and faint amber gradient. No planned/dimmed sprint links.
- Footer card: the live status the backend reports (`● API NOMINAL` today; collector freshness later), plus a one-line read-only statement and the last check time.

---

## 4. Components

Build these as shared components in `frontend/src/components/vyom/`, each one when a surface first needs it. Names are suggestions.

| Component | Spec |
|---|---|
| `SectionLabel` | Mono uppercase label, optional number prefix `NN /`. |
| `StatusBadge` | Mono 10px uppercase with a glyph: `■ ALERT`, `▲ CAUTION`, `● NOMINAL`. Status tint recipe. Radius 4. |
| `ImpactPill` | `HIGH IMPACT` (alert), `MED IMPACT` (caution) or `LOW IMPACT` (agent), on a tinted pill, radius 999. |
| `Delta` | Mono, `▲ 6%` / `▼ 3d` / `— 0`, coloured by **effect** (see the semantic rule). |
| `Button` variants | **primary**: `--vy-text` fill, `--vy-bg` text, weight 600. **agent**: `--vy-agent` fill, `--vy-agent-ink` text. **agent-ghost**: `--vy-agent-bg` fill, `--vy-agent-line` border, `--vy-agent` text. **secondary**: `--vy-surface-3` fill, `--vy-line` border. **ghost**: transparent, `--vy-text-3`. |
| `SegmentedTabs` | Pill container (`--vy-line` border, 3px padding). The active tab is a `--vy-text` fill with `--vy-bg` text; others are transparent, `--vy-text-3`. Counts sit in mono after the label. |
| `MetricCard` | `--vy-surface-2`, `--vy-line` border, radius 10–12. Title 14px, value 26–34px/600, optional delta, impact pill and ↗ link. Inverted variant (light `--vy-text` fill, navy text) for **one** hero card per screen, such as "Biggest mover". |
| `FindingRow` | Score (22px/600, coloured by type), title, mono resource path, `StatusBadge`, metric + mono relative time (`T−6h`). |
| `FindingCard` (expanded) | Tinted alert border/bg. Header: score + `RISK` label, title, mono path, badge, "T−3h · via terraform apply". Then three columns (each separated by a hairline): **Evidence** (claim + mono API source), **Agent read** (prose + confidence meters), **Why this needs you** (tinted). Footer actions: primary *Open evidence ↗*, agent-ghost *Ask Vyom about this*, secondary *Related resources · N linked*, ghost *Acknowledge*. (The mockup's *Draft Terraform fix* is outside the core.) |
| `EvidenceItem` | 14px claim with an 11px mono source underneath (`rds:DescribeDBInstances`). |
| `ConfidenceMeter` | 64×3px track, fill in `--vy-text` (high) or `--vy-caution` (low), mono label `HIGH`/`LOW`. |
| `Citation` | Superscript mono `[1]` in `--vy-agent`, plus a source chip row (mono 10px, `--vy-line` border). |
| `PipelineStrip` | Five equal cells following a question's path: `01 API → 02 REASON → 03 K8S MCP → 04 AWS MCP → 05 GROUND`. Each has a 2px top border in its status colour, a mono code, a name and a mono detail. A stage the backend does not report yet is `○` not reported. |

### 4.1 Agent panel (`AskVyom`), the most prominent element on Today
- Sits directly under the greeting, full width. Agent gradient bg (`--vy-agent-bg` → `#081633`), `--vy-agent-line` border, radius 10, soft blue outer glow.
- Header: pulsing `● ASK VYOM · AGENT ONLINE` in mono agent colour, and `read-only · cites every answer` on the right.
- Large textarea (17px) in a `--vy-surface-1` well. Footer row: scope (set by the server, shown, not chosen in the browser), the tools the host has really enabled in mono (for example `k8s-mcp`; an AWS integration appears only once R7 enables one; coloured `--vy-ok` when connected), agent button *Ask ↵*.
- **Not-connected state**: hollow dot, `ASK VYOM · AGENT NOT CONNECTED`, the form disabled, and one sentence saying why. Model or tool failure is shown the same way, never as a guessed answer.
- **Mode tiles** arrive with the workflows they start: `HEALTH` Which workloads are unhealthy (R3), `INVESTIGATE` Investigate a workload (R4), `POSTURE` Explain a finding (R5). No `DRAFT` or `REPORT` tile: Vyom does not draft fixes or compliance reports.
- **Suggested chips**: the supported questions for the current scope; when supported, derived from open issues/findings (pill buttons).
- Right column: **last answer** with its question, a short answer with citations, source chips (`k8s-mcp pods_list`, `k8s events`) and, once scoped investigation history exists, *CONTINUE THREAD →*.

---

## 5. Data-viz patterns

General: no chart junk, no gridlines beyond a baseline, mono axis labels at 9–10px, and colour only by status/agent. Everything has an `aria-label` summary.

| Pattern | Use | Spec |
|---|---|---|
| **Diff list** | "What changed since Monday" | Mono table in a `--vy-surface-1` well. Header `@@ mon 06 oct → today @@ posture.state` in agent colour. Rows: a sign gutter (`+` / `−` / `~`, 28px, divider right), count, kind, detail (truncate). Riskier rows get an alert tint (8%) and sign; safer rows an ok tint (7%); neutral rows are untinted with a `--vy-text-4` sign. |
| **Split-diff strips** | Inventory by state, before vs now | Two strips of about 160 marks (1 mark ≈ N resources). `− MON` on top (28–30px, red-tinted gutter frame), `+ NOW` below (40–42px, green-tinted frame), with a 16px **link row** between. Unchanged marks are dimmed (opacity 0.28 / 0.4). **Changed marks are full opacity with a 1px ring and a 10px glow**: `--vy-ok` if safer, `--vy-alert` if riskier. The link row draws a gradient line (old colour → new colour) only under changed marks. Footer: legend + "7 safer · 5 riskier". |
| **Score drivers** | What moves the score | 3×2 grid of `MetricCard`s with value, delta and `ImpactPill`. |
| **Change history calendar** | 30-day per-org activity | One row per org, 30 dots (8px, 3px gap). States: no change `--vy-line`, clean change `--vy-quiet`, drift `--vy-caution`, introduced finding `--vy-alert` with a `×` and a glow. |
| **Rule matrix** | Findings per rule family (R5/R8) | One 11px rounded square per rule, grouped by category. Pass `--vy-quiet-2`, warn `--vy-caution`, fail `--vy-alert`, unknown hollow. Header shows `N FAIL  passed/total`. Framework labels are metadata, never a certification score. |
| **Hatched bars** | Secondary bars | Non-highlighted bars use a diagonal hatch (`repeating-linear-gradient(135deg, rgba(108,180,255,.22) 0 2px, transparent 2px 7px)`) on `--vy-surface-3` with a `--vy-line-strong` border. Only the highlighted bar is solid (agent colour, or a gradient to `--vy-royal`). |
| **Annotated line** | A health metric over an issue's timeline (restarts, ready replicas) | Agent-colour line + gradient area fill. A vertical dashed **caution** marker + dot at the change event, with a caption naming the change (`Oct 9 · image tag changed …`). Temporal evidence, not proof of cause. |
| **Blast-radius graph** | Finding → linked resources | See §6.2. |

Use **visx** or plain SVG/flex for the custom patterns (diff strips, matrix, history). Use Recharts only for standard line/area charts, and theme it with the tokens.

---

## 6. Screens

### 6.1 Overview (`/`)
The layout below adapts the mockup's Today page into the operations overview. Built so far: items 1–4, with real API, agent and evidence state only. Items 5–7
arrive per §0, narrowed to what Vyom collects (workload health, restarts, unavailable replicas,
changes, issues, findings and freshness).

Top to bottom:
1. Header ticker.
2. `00 / FLIGHT STATUS`: greeting headline in plain, specific language ("Evening, Darshan. Two things need a human."), a one-paragraph summary naming the top issues, and a time-range control.
3. **AskVyom panel** (§4.1).
4. `PipelineStrip`.
5. `01 / POSTURE` panel. Header row: label plus an All / AWS / EKS `SegmentedTabs`. Body, in two columns: **Diff list** | **Split-diff strips**. There is **no gauge and no single big score number**.
6. `01.1 / WHAT MOVES THE SCORE` (driver cards) next to `01.2 / CHANGE HISTORY · 30 DAYS`.
7. Two columns:
   - **Left:** `02 / FINDINGS` with `SegmentedTabs` (Needs a human / Acknowledged / Resolved), one expanded `FindingCard`, then `FindingRow`s, and a footer `5 OF 23 OPEN` and `ALL FINDINGS →`.
   - **Right rail:** `03 / ISSUES` (open episodes with investigation progress + `ALL ISSUES →`), `04 / FRESHNESS` (collection coverage per connection: complete, partial, stale, denied), and `05 / FOUND OVERNIGHT` (detected changes and automatic investigation results + *Continue in chat →*).

### 6.2 Blast radius (`/findings/:id/blast-radius`)
For Vyom this is the resource relationship view of a finding: the affected workload at the core,
with categories Owners (Deployment, ReplicaSet), Pods, Services (by selector), Nodes and Events.
The security-group, IAM and data-class categories in the mockup are outside the core.

- Top bar: back button, logo, `■ ALERT · BLAST RADIUS` label and title; Graph/Table toggle, `DEPTH 2 ▾`, agent button *Ask Vyom about this path*.
- **Graph canvas** (min 1080×780, scrolls horizontally on small screens):
  - **Core orb** on the left: a radial-gradient sphere in the status colour, its score in the centre, concentric glow rings, a mono resource id above and a tag below (`PUBLIC · PII`).
  - **Five category cards** stacked in the middle: Security groups, Network paths, Workloads, IAM principals, Data classes. Each card has an icon square, a count and a label. They connect to the core with hairline bezier curves; the selected one turns agent-colour with a glow.
  - **Leaves fanned on an arc** (radius about 400) from the selected card. Each leaf is a glowing dot coloured by state, a mono name, a state tag and an account tag. Bezier links are coloured by leaf state at 75% opacity.
  - Clicking a category re-fans the leaves and updates the readout.
- **Agent readout aside** (about 380px): `VYOM READOUT`, prose for the selected category, **shortest exposure path** as a stacked mono chain (first hop alert-bordered), an "If you restrict ingress" impact table, and actions (mockup: *Draft Terraform fix ↗* / *Show the 3 unknown IPs*; for Vyom: *Open evidence ↗* / *Ask Vyom about this path*).
- Implementation: React Flow or d3-hierarchy for layout. Keep the visual (orb, arc fan, beziers) regardless of library.

## 7. Copy & voice
- Plain, specific, confident; borrow mission-control words lightly (NOMINAL, CAUTION, ALERT, telemetry, flight kit). Don't overdo the space theme in body text.
- Say *who / what / when*: "Opened 3 h ago by terraform apply", "Changed by role [ci-deploy]".
- Relative times in mono: `T−3h`, `T−1d`, `TODAY`.
- Never claim an action Vyom can't take; the read-only promise appears in the sidebar footer and the agent panel header.

## 8. Accessibility
- Text contrast ≥ 4.5:1 (all `--vy-text*` tokens pass on `--vy-surface-2`; don't put `--vy-text-4` on `--vy-surface-3` for body text).
- Status is never colour-only: it always has a glyph (■ ▲ ● ◆), sign (+ − ~) or label.
- Real `<button>` / `<a>` elements; tabs use `role="tablist"`/`tab`; icon-only buttons get `aria-label`; every chart has an `aria-label` summary.
- Respect `prefers-reduced-motion` for the pulsing agent dot and any glow animation.

## 9. Do / Don't
- **Do** reuse the tokens; never hardcode a hex in a component.
- **Do** put identifiers in mono.
- **Don't** add gradient washes to cards (gradients are only for the page bg, the agent panel, the run-rate block and the orb), emoji, drop shadows on cards, or green for "healthy resources" (use `--vy-quiet`).
- **Don't** reintroduce a gauge or a single composite score on Today without a design decision.
