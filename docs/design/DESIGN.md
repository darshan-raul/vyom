# Vyom — Frontend Design Spec

> Source of truth for how Vyom's UI looks. Owner-supplied on 12 October 2026 and adapted here to
> the [constitution](../../vyom-12-week-sprint-plan.md): what Vyom shows, and when, follows the
> sprint plan (§0). Reference mockups live in [mockups/](mockups/) (`*.dc.html`). They are
> design-tool source (HTML markup + inline styles + a small logic class), not runnable pages; read
> them for exact layout, values and sample copy. When this spec and a mockup disagree, this spec
> wins. When this spec and the constitution disagree on scope, the constitution wins.
> Stack: React + Refine + shadcn/ui + Tailwind.
> Logo in the app: [vyom-logo.png](vyom-logo.png), the circular transparent mark; see
> [branding](../BRANDING.md).

---

## 0. Scope and rollout

The mockups show the dense end state with sample data for a multi-organization AWS estate. Vyom
gets there one sprint at a time, and each surface appears only when the backend serves real data
for it. Until then the surface is either absent or shows an explicit "not connected" state. Nothing
is filled with sample numbers.

Vyom's subject is **one AWS account (initially `ap-south-1`) and one Kubernetes cluster per
environment**, read-only. Where the mockups say "organizations", read account, cluster and
namespace.

| Sprint | What the UI gains | Spec elements it uses |
|---|---|---|
| S1 (built) | App shell, tokens and fonts, Today with the API's own liveness, the question-path strip | §2, §3, `SectionLabel`, `PipelineStrip` |
| S1.5 (built) | Ask Vyom is live: one question, one tool call, an answer with citations, the tool called, the resources read, the collection time and the trace ID; a fixed reason when there is no answer | §4.1, `Citation`, evidence rows |
| S1.6 (built) | Kubernetes view (`/kubernetes`): pods table from the direct collector with source, collection time, coverage and loading, empty, denied, missing, partial and stale states; the ticker counts pods by state | `StatusBadge`, header ticker counts, wide table in an `overflow-x` box |
| S2 | AWS view: EC2 inventory and CloudWatch CPU/status charts; workload and node health; current CPU and memory | `MetricCard`, `Delta`, annotated line, scope tabs All / AWS / EKS |
| S3 | Runbook citations in answers, chat history ("last answer", continue thread), freshness of scheduled observations | `Citation` source chips, last-answer column |
| S4 | Findings (unavailable replicas, repeated restarts), bounded investigation, related-resource graph, daily cost by service | `FindingRow`, `FindingCard`, `ConfidenceMeter`, blast-radius layout (§6.2), dot-matrix spend, "by service" list (§6.3) |
| S6 | Identity: who is signed in, tenant scope in the sidebar | scope switcher card |

**In the mockups but outside the 12-week core** (see "Keep out" in the constitution). Do not build
these without a constitution change: multi-organization switching and per-org charts, exposure and
security-group findings, CVE or software-risk findings, compliance matrices, Terraform drift and
"Draft Terraform fix", CloudTrail-sourced "who changed it", idle-resource and savings
recommendations, forecasts and account leaderboards. The patterns that carry them (diff list,
split-diff strips, change-history calendar, compliance matrix, share strip) stay specified in §5 so
a later milestone can use them.

**Vyom-specific states.** Evidence can be missing, partial, stale, denied or zero, and these are
different. A source that reports nothing is drawn with the hollow glyph `○` and `--vy-text-4`
("not reported"), never as nominal and never as zero.

---

## 1. Principles

1. **Mission-control console, not a SaaS template.** Dark navy, hairline borders, monospace labels. Calm by default; colour only where something needs attention.
2. **Colour = state, never decoration.** Status colours (alert / caution / nominal) appear only on things with that status. Healthy resources are quiet blue, not green.
3. **The agent is a first-class surface.** Sky blue (`--vy-agent`) belongs to Vyom's agent: the Ask panel, agent-found items, citations, savings. Don't use it for anything else.
4. **Show change, not just state.** Prefer "what changed since X" (diffs, before/after, deltas) over static totals. A finding should say *what changed, who changed it, and when*.
5. **Every claim is traceable.** Agent answers and evidence carry citations to the API call / CloudTrail event / runbook they came from (`ec2:DescribeSecurityGroups`, `runbook/db-network-access`).
6. **Read-only is visible.** Primary actions are *ask* / *open the runbook* / *acknowledge*, never *remediate*. Vyom reads; it does not change a cluster or an account, and it does not draft changes in this roadmap.
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
  --vy-caution:     #F5B84A;  /* drift, software risk, anomaly, over forecast */
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
- Header ticker (top of main): mono 11px status counts plus a timestamp, with a hairline under it. On Today it carries the API and agent state; on Kubernetes it counts pods by state (`● 1 NOMINAL  ▲ 0 CAUTION  ■ 1 ALERT`); from S2 nodes and instances as well.

### Sidebar
- Logo (circular image, 40–44px, faint blue halo) + `VYOM` wordmark (19px/700, tracking 0.22em) + mono sub-label `AWS · K8S · ALPHA`.
- Scope card (account, region, cluster, namespace) once the API serves the trusted context; it becomes a switcher only with tenants in S6. Search (with a `⌘K` hint) arrives with something to search.
- Nav groups with mono section labels. `OPERATE`: `01` Today, `02` Kubernetes, `03` AWS, `04` Findings, `05` Spend. `FLIGHT KIT`: Runbooks, History. The active item gets a **2px amber left border** and a faint amber gradient; badges use the alert colour in mono (`2 NEW`). A surface that is planned but not built is listed dimmed with its sprint in mono (`S2`) and is not a link.
- Footer card: the live status the backend reports (`● API NOMINAL` today; collector freshness later), plus a one-line read-only statement and the last check time.

---

## 4. Components

Build these as shared components in `frontend/src/components/vyom/`, each one when a surface first needs it. Names are suggestions.

| Component | Spec |
|---|---|
| `SectionLabel` | Mono uppercase label, optional number prefix `NN /`. |
| `StatusBadge` | Mono 10px uppercase with a glyph: `■ ALERT`, `▲ CAUTION`, `● NOMINAL`, `◆ SPEND`. Status tint recipe. Radius 4. |
| `ImpactPill` | `HIGH IMPACT` (alert), `MED IMPACT` (caution) or `LOW IMPACT` (agent), on a tinted pill, radius 999. |
| `Delta` | Mono, `▲ 6%` / `▼ 3d` / `— 0`, coloured by **effect** (see the semantic rule). |
| `Button` variants | **primary**: `--vy-text` fill, `--vy-bg` text, weight 600. **agent**: `--vy-agent` fill, `--vy-agent-ink` text. **agent-ghost**: `--vy-agent-bg` fill, `--vy-agent-line` border, `--vy-agent` text. **secondary**: `--vy-surface-3` fill, `--vy-line` border. **ghost**: transparent, `--vy-text-3`. |
| `SegmentedTabs` | Pill container (`--vy-line` border, 3px padding). The active tab is a `--vy-text` fill with `--vy-bg` text; others are transparent, `--vy-text-3`. Counts sit in mono after the label. |
| `MetricCard` | `--vy-surface-2`, `--vy-line` border, radius 10–12. Title 14px, value 26–34px/600, optional delta, impact pill and ↗ link. Inverted variant (light `--vy-text` fill, navy text) for **one** hero card per screen, such as "Biggest mover". |
| `FindingRow` | Score (22px/600, coloured by type), title, mono resource path, `StatusBadge`, metric + mono relative time (`T−6h`). |
| `FindingCard` (expanded) | Tinted alert border/bg. Header: score + `RISK` label, title, mono path, badge, "T−3h · via terraform apply". Then three columns (each separated by a hairline): **Evidence** (claim + mono API source), **Agent read** (prose + confidence meters), **Why this needs you** (tinted). Footer actions: primary *Open runbook ↗*, agent-ghost *Ask Vyom about this*, secondary *Related resources · N linked*, ghost *Acknowledge*. (The mockup's *Draft Terraform fix* is outside the core.) |
| `EvidenceItem` | 14px claim with an 11px mono source underneath (`rds:DescribeDBInstances`). |
| `ConfidenceMeter` | 64×3px track, fill in `--vy-text` (high) or `--vy-caution` (low), mono label `HIGH`/`LOW`. |
| `Citation` | Superscript mono `[1]` in `--vy-agent`, plus a source chip row (mono 10px, `--vy-line` border). |
| `PipelineStrip` | Five equal cells following a question's path: `01 API → 02 REASON → 03 K8S MCP → 04 AWS MCP → 05 GROUND`. Each has a 2px top border in its status colour, a mono code, a name and a mono detail. A stage the backend does not report yet is `○` not reported. |

### 4.1 Agent panel (`AskVyom`), the most prominent element on Today
- Sits directly under the greeting, full width. Agent gradient bg (`--vy-agent-bg` → `#081633`), `--vy-agent-line` border, radius 10, soft blue outer glow.
- Header: pulsing `● ASK VYOM · AGENT ONLINE` in mono agent colour, and `read-only · cites every answer` on the right.
- Large textarea (17px) in a `--vy-surface-1` well. Footer row: scope (set by the server, shown, not chosen in the browser), the tools the host has really enabled in mono (`k8s-mcp` in S1, `aws-mcp` in S2, `runbooks` in S3; coloured `--vy-ok` when connected), agent button *Ask ↵*.
- **Not-connected state**: hollow dot, `ASK VYOM · AGENT NOT CONNECTED`, the form disabled, and one sentence saying why. Model or tool failure after S1.5 is shown the same way, never as a guessed answer.
- **Mode tiles** arrive with the workflows they start: `HEALTH` Which workloads are unhealthy (S2), `INVESTIGATE` Investigate a workload (S4), `EXPLAIN` Explain service cost (S4). No `DRAFT` or `REPORT` tile: Vyom does not draft fixes or compliance reports in this roadmap.
- **Suggested chips**: the supported questions for the current scope; from S4, generated from open findings (pill buttons).
- Right column: **last answer** with its question, a short answer with citations, source chips (`k8s-mcp pods_list`, `runbook/image-pull`) and, once history exists in S3, *CONTINUE THREAD →*.

---

## 5. Data-viz patterns

General: no chart junk, no gridlines beyond a baseline, mono axis labels at 9–10px, and colour only by status/agent. Everything has an `aria-label` summary.

| Pattern | Use | Spec |
|---|---|---|
| **Diff list** | "What changed since Monday" | Mono table in a `--vy-surface-1` well. Header `@@ mon 06 oct → today @@ posture.state` in agent colour. Rows: a sign gutter (`+` / `−` / `~`, 28px, divider right), count, kind, detail (truncate). Riskier rows get an alert tint (8%) and sign; safer rows an ok tint (7%); neutral rows are untinted with a `--vy-text-4` sign. |
| **Split-diff strips** | Inventory by state, before vs now | Two strips of about 160 marks (1 mark ≈ N resources). `− MON` on top (28–30px, red-tinted gutter frame), `+ NOW` below (40–42px, green-tinted frame), with a 16px **link row** between. Unchanged marks are dimmed (opacity 0.28 / 0.4). **Changed marks are full opacity with a 1px ring and a 10px glow**: `--vy-ok` if safer, `--vy-alert` if riskier. The link row draws a gradient line (old colour → new colour) only under changed marks. Footer: legend + "7 safer · 5 riskier". |
| **Score drivers** | What moves the score | 3×2 grid of `MetricCard`s with value, delta and `ImpactPill`. |
| **Change history calendar** | 30-day per-org activity | One row per org, 30 dots (8px, 3px gap). States: no change `--vy-line`, clean change `--vy-quiet`, drift `--vy-caution`, introduced finding `--vy-alert` with a `×` and a glow. |
| **Compliance matrix** | Controls per framework | One 11px rounded square per control, grouped by family. Pass `--vy-quiet-2`, warn `--vy-caution`, fail `--vy-alert`. Header shows `N FAIL  passed/total`. |
| **Dot-matrix spend** | Daily spend + projection | A column of 8px dots per day. Actual `--vy-quiet`, anomaly dots `--vy-caution`, today `--vy-agent`, **agent projection = hollow agent-colour dots** at 70% opacity. |
| **Share strip** | Spend by org | Pill per org, its width proportional to share (`flex-grow` = %), with a coloured initial badge, amount and mono %. |
| **Hatched bars** | Secondary bars | Non-highlighted bars use a diagonal hatch (`repeating-linear-gradient(135deg, rgba(108,180,255,.22) 0 2px, transparent 2px 7px)`) on `--vy-surface-3` with a `--vy-line-strong` border. Only the highlighted bar is solid (agent colour, or a gradient to `--vy-royal`). |
| **Annotated line** | Daily cost per account | Agent-colour line + gradient area fill. A vertical dashed **caution** marker + dot at the change event, with a caption naming the change (`Oct 9 · terraform apply moved …`). |
| **Blast-radius graph** | Finding → linked resources | See §6.2. |

Use **visx** or plain SVG/flex for the custom patterns (diff strips, dot matrix, matrix, history). Use Recharts only for standard line/area charts, and theme it with the tokens.

---

## 6. Screens

### 6.1 Today (`/`)
The end state below is the mockup's. Built so far: items 1–4, with real API, agent and evidence state only. Items 5–7
arrive per §0, with posture and findings narrowed to what Vyom collects (workload health, restarts,
unavailable replicas, EC2 state, daily cost).

Top to bottom:
1. Header ticker.
2. `00 / FLIGHT STATUS`: greeting headline in plain, specific language ("Evening, Darshan. Two things need a human."), a one-paragraph summary naming the top issues, and a time-range control.
3. **AskVyom panel** (§4.1).
4. `PipelineStrip`.
5. `01 / POSTURE` panel. Header row: label plus an All / AWS / EKS `SegmentedTabs`. Body, in two columns: **Diff list** | **Split-diff strips**. There is **no gauge and no single big score number**.
6. `01.1 / WHAT MOVES THE SCORE` (driver cards) next to `01.2 / CHANGE HISTORY · 30 DAYS`.
7. Two columns:
   - **Left:** `02 / FINDINGS` with `SegmentedTabs` (Needs a human / Acknowledged / Resolved), one expanded `FindingCard`, then `FindingRow`s, and a footer `5 OF 23 OPEN` and `ALL FINDINGS →`.
   - **Right rail:** `03 / SPEND · MTD` (dot-matrix + `OPEN SPEND →`), `04 / COMPLIANCE` matrix, and `05 / FOUND OVERNIGHT` (agent items with mono type badges IDLE / DRIFT / EXPIRY + *Review N in chat →*).

### 6.2 Blast radius (`/findings/:id/blast-radius`)
For Vyom this is the S4 related-resources view of a finding: the affected workload at the core,
with categories Owners (Deployment, ReplicaSet), Pods, Services (by selector), Nodes and Events.
The security-group, IAM and data-class categories in the mockup are outside the core.

- Top bar: back button, logo, `■ ALERT · BLAST RADIUS` label and title; Graph/Table toggle, `DEPTH 2 ▾`, agent button *Ask Vyom about this path*.
- **Graph canvas** (min 1080×780, scrolls horizontally on small screens):
  - **Core orb** on the left: a radial-gradient sphere in the status colour, its score in the centre, concentric glow rings, a mono resource id above and a tag below (`PUBLIC · PII`).
  - **Five category cards** stacked in the middle: Security groups, Network paths, Workloads, IAM principals, Data classes. Each card has an icon square, a count and a label. They connect to the core with hairline bezier curves; the selected one turns agent-colour with a glow.
  - **Leaves fanned on an arc** (radius about 400) from the selected card. Each leaf is a glowing dot coloured by state, a mono name, a state tag and an account tag. Bezier links are coloured by leaf state at 75% opacity.
  - Clicking a category re-fans the leaves and updates the readout.
- **Agent readout aside** (about 380px): `VYOM READOUT`, prose for the selected category, **shortest exposure path** as a stacked mono chain (first hop alert-bordered), an "If you restrict ingress" impact table, and actions (mockup: *Draft Terraform fix ↗* / *Show the 3 unknown IPs*; for Vyom: *Open runbook ↗* / *Ask Vyom about this path*).
- Implementation: React Flow or d3-hierarchy for layout. Keep the visual (orb, arc fan, beziers) regardless of library.

### 6.3 Spend (`/spend`)
For Vyom this is the S4 daily Cost Explorer view: totals and the "by service" list for one account
over a bounded date range, with source, date and freshness. Billing is never described as
real-time. Forecast, savings, per-org share and the account leaderboard are outside the core.

- Top bar: back, logo, `03 / SPEND`; org filter chips (pill, coloured dot, the active one inverted); date range; export.
- Headline row:
  - Big MTD number (64px; decimals in `--vy-quiet`) with a caution `▲ %` pill and a filled `+$ vs fcst` pill, plus a mono source line ("CUR line items · refreshed 6m ago").
  - Top account card.
  - **Inverted "Biggest mover" card.**
  - Three small centred metrics: Forecast, **Savings found** (agent-highlighted) and Untagged %.
- **Share strip** by org.
- Left column:
  - "By service" list: rows with a mono service code chip, name, amount and % pill. The anomalous service's chip is caution-filled.
  - "By environment" hatched bars, with prod solid.
  - **Run-rate panel**: a royal-blue gradient left block (cost/day, resources, cost/resource) and a right block with 3-month grouped hatched bars, a Cost/Usage/Waste toggle and an agent-colour value flag on each month.
- Right column: **account leaderboard** with columns Account, MTD, Findings (critical count pill in alert + other count), Score, Δ forecast (coloured by effect) and a chevron.
  - Clicking a row **expands it in place**: agent-gradient background, a 2px agent left border, context chips (the last one an agent chip such as "Vyom: 3 savings ›"), a breakdown of three cards, and an **annotated daily-cost line**.

---

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
