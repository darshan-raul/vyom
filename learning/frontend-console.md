# Guide 4 — The console: how the UI is put together

This guide assumes you are comfortable with backends and less so with frontends. It explains the browser side of Vyom from the ground up: what runs where, how a number gets from the API onto the screen, and why the page looks the way it does. Read guides [2](chat-graph.md) and [3](direct-pod-view.md) first; this is the other end of the two routes they describe.

Everything described here is in `frontend/`. The look is specified in [docs/design/DESIGN.md](../docs/design/DESIGN.md), which you supplied; this guide explains how the code implements it.

Section 8 has questions to answer out loud.

---

## 1. The whole thing in plain words

The UI is a program that runs **in your browser**, not on a server. It has one job: ask the backend for JSON, and draw it. It holds no credentials, makes no decisions about what you may see, and cannot reach Kubernetes, MCP or the model. If you deleted the frontend, nothing about what Vyom is allowed to do would change.

That gives one rule that explains most of the code:

> **The UI shows only what the backend reports, and says so plainly when the backend reports nothing.**

There is no sample data anywhere. A value the backend did not send is drawn as "not reported", never as zero and never as healthy.

**An analogy.** The backend is the instrument cluster's sensors and wiring; the UI is the glass and the needles. A needle with no signal should sit on a marked "no signal" position, not on a comfortable-looking number.

---

## 2. What runs where

In development there are two processes, and it is worth being clear about which is which:

```
 browser tab                 Vite dev server              FastAPI backend
 http://127.0.0.1:5173       127.0.0.1:5173               127.0.0.1:8000
 ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
 │ React app        │  GET / │ serves the app's │        │ /api/health      │
 │ (runs here)      │───────>│ JavaScript + CSS │        │ /api/agent       │
 │                  │        │                  │        │ /api/chat        │
 │ fetch('/api/…') ─┼───────>│ proxies /api/* ──┼───────>│ /api/kubernetes… │
 └──────────────────┘        └──────────────────┘        └──────────────────┘
```

- **Vite** is the development server and the build tool. `npm run dev` starts it. It turns the TypeScript and CSS in `frontend/src` into something a browser can run, and reloads the page when you save a file.
- The app always calls `/api/...` on **its own address** (same origin). Vite forwards those to the backend. That one line of config is in `frontend/vite.config.ts`:

  ```ts
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000' } }
  ```

  Because the browser only ever talks to one origin, there is no CORS configuration anywhere. In S1.7 an nginx container will play Vite's role: serve the built files and forward `/api`.
- `npm run build` produces static files in `frontend/dist`. No Node process is needed in production.

Something to notice in the failure messages: when the backend is down, the UI says "The backend answered 502". The 502 comes from Vite's proxy failing to connect, not from the backend.

---

## 3. The stack, one layer at a time

Each layer exists to solve one problem. Start at the bottom.

| Layer | Problem it solves | Where you see it |
|---|---|---|
| **TypeScript** | JavaScript with types, so a misspelt field is an error before it runs | every `.ts` / `.tsx` file |
| **React** | Describe the screen as a function of data; React updates the page when the data changes | every component |
| **TanStack Query** (inside Refine) | Fetching, re-fetching on a timer, remembering the last result, knowing "loading / error / success" | `useCustom`, `useCustomMutation` |
| **Refine** | A standard way to plug an API into those hooks: the *data provider* | `dataProvider.ts`, `<Refine>` in `App.tsx` |
| **React Router** | Different pages at different addresses | `App.tsx`, `sidebar.tsx` |
| **Tailwind CSS** | Styling by small class names in the markup (`flex gap-3 text-sm`) | every `className` |
| **shadcn/ui** | Ready-made accessible components, copied into the repo as source you own | `components/ui/` |

### 3.1 React in three sentences

A **component** is a function that returns markup. Its inputs are **props**. When data it depends on changes, React calls the function again and updates only what differs on the page.

```tsx
export function StatusText({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={toneText[tone]}>{toneGlyph[tone]} {children}</span>
}
```

A **hook** is a function whose name starts with `use`. It lets a component hold on to something between calls: a piece of state (`useState`), or the result of a fetch (`useCustom`).

### 3.2 The data provider: the only door to the API

`frontend/src/dataProvider.ts` is the single place a network request is made:

```ts
custom: async ({ url, method, payload }) => {
  // fetch(url, { method, headers, body }) …
  if (!response.ok) throw { message: `The backend answered ${response.status}`, statusCode: response.status }
  return { data: await response.json() }
}
```

- Every call in the UI goes through this function. If you want to know everything the browser can ask the backend, read the four hooks in section 4; there is nothing else.
- An unreachable backend and a non-200 answer both become a thrown object with a message. The hooks turn that into an "error" state.
- The other Refine methods (`getList`, `create`, …) are stubs that reject with 501. Vyom has no create, update or delete; the UI is read-only like everything else.

### 3.3 shadcn/ui: components you own

shadcn/ui is not a library you install and import. Its command copies component source files into `frontend/src/components/ui/`. They are yours to read and edit: `alert.tsx`, `badge.tsx`, `button.tsx`, `card.tsx`, `table.tsx`, `textarea.tsx`. They get their colours from CSS variables such as `--primary` and `--border`, which is what section 5 hooks into.

---

## 4. How data reaches the screen

There are exactly four conversations between the UI and the backend. Each is one hook in `frontend/src/lib/`.

| Hook | File | Request | How often | Feeds |
|---|---|---|---|---|
| `useApiHealth` | `lib/api-health.ts` | `GET /api/health` | every 10 s | sidebar footer, Today's ticker and first strip cell |
| `useAgentStatus` | `lib/agent.ts` | `GET /api/agent` | every 30 s, only while the API is up | Ask panel (scope, tools, enabled or not), strip |
| `useAsk` | `lib/agent.ts` | `POST /api/chat` | when you press Ask | the answer column, strip, ticker |
| `usePods` | `lib/pods.ts` | `GET /api/kubernetes/pods` | every 15 s | the Kubernetes page |

### 4.1 A read on a timer

```ts
const { query } = useCustom<Health>({
  url: '/api/health',
  method: 'get',
  queryOptions: { retry: false, refetchInterval: 10_000 },
  errorNotification: false,
})
```

`query` has `isPending`, `isError`, `error`, `data`, and timestamps. The hook then folds those into one small value that the rest of the UI uses:

```ts
type ApiHealth =
  | { state: 'checking' }
  | { state: 'unreachable'; message: string; checkedAt: number }
  | { state: 'ok'; status: string; service: string; version: string; checkedAt: number }
```

This is a **discriminated union**: three shapes, told apart by `state`. TypeScript will not let a component read `version` without first checking `state === 'ok'`. It is the frontend version of the backend's "missing is not zero": the type makes it impossible to draw a version number while the API is unreachable.

### 4.2 An action

Asking a question is not a read on a timer; it happens when you click. That is a **mutation**:

```ts
const { mutate, mutation } = useCustomMutation<ChatResult>()
mutate({ url: '/api/chat', method: 'post', values: { question } })
```

Look at `values: { question }`. That is the whole request body. The UI knows the namespace (it displays it), and still does not send it. The backend would reject it with a 422 if it did (guide 2, section 5.1).

### 4.3 Keeping the last good value

`usePods` returns four things: `view` (the last successful response), `pending`, `failed`, `fetchedAt`. TanStack Query keeps the previous data when a later fetch fails. The Kubernetes page uses that deliberately: if the backend goes away, the table stays on screen, the state chip turns to `stale`, and an alert says when the data is from. Old-and-labelled is more useful than blank, as long as it is labelled.

### 4.4 The types mirror the backend

`lib/agent.ts` declares `Evidence`, `EvidenceItem`, `ChatResult`, `AgentStatus` by hand, matching `backend/src/vyom/evidence.py` and `api/app.py`. Nothing generates them. If a backend field is renamed, TypeScript will not notice; the UI will just show a blank. Keep that in mind when changing the evidence contract. (Generating these from the API's OpenAPI schema would close the gap; it has not been needed yet.)

---

## 5. Why it looks the way it does

### 5.1 Tokens

A **design token** is a named value: a colour, a size. Components use the name, never the raw value, so the whole look can be changed in one file. Vyom's are CSS variables in `frontend/src/index.css`:

```css
:root {
  --vy-bg: #050C1F;         /* page */
  --vy-surface-2: #0A1633;  /* panels */
  --vy-line: #1C2F57;       /* borders */
  --vy-text: #EAF1FF;       /* primary text */
  --vy-agent: #6CB4FF;      /* the agent, and only the agent */
  --vy-alert: #FF6F5E;  --vy-caution: #F5B84A;  --vy-ok: #4FD1A5;
  --vy-quiet: #4C6FB0;      /* healthy things in charts: blue, not green */
}
```

Two bridges make those names usable everywhere:

- **To shadcn**: `--background: var(--vy-bg); --border: var(--vy-line); …`. The copied shadcn components read `--background` and so on, so they pick up the theme without being edited.
- **To Tailwind**: the `@theme inline` block declares `--color-vy-agent: var(--vy-agent)`, which makes Tailwind generate classes such as `text-vy-agent`, `bg-vy-surface-2`, `border-vy-line`.

So `className="border border-vy-line bg-vy-surface-2"` means: a one-pixel border in the line colour, on the panel colour. No hex code appears in any component; that is rule one of the spec's "Do / Don't".

`text-vy-alert/35` means that colour at 35% opacity. The spec's "status tint recipe" (coloured text, about 35% border, about 8% fill) is one line in `lib/status.ts`:

```ts
alert: 'border-vy-alert/35 bg-vy-alert/8 text-vy-alert'
```

### 5.2 Colour means state

The spec's second principle: colour is for status, never decoration. `lib/status.ts` is where that is encoded:

| Tone | Glyph | Colour | Means |
|---|---|---|---|
| `ok` | ● | green | a real exchange succeeded |
| `caution` | ▲ | amber | degraded, partial, stale |
| `alert` | ■ | red | failed, denied |
| `idle` | ○ | dim | **not reported**: nothing has told us either way |

Every status has a glyph as well as a colour, so it reads without colour vision.

`idle` is the important one, and it is Vyom-specific. Look at the question-path strip on Today before you ask anything: the model and MCP cells show a hollow `○` and the word "configured". They do **not** show green, because `GET /api/agent` only reports configuration; nobody has proven the model is reachable. After you ask a question, the cells take their tone from what actually happened: green if the model replied and evidence was complete, red if not. The function is `stages()` in `pages/today.tsx`; read it as the place where "configured is not healthy" is implemented.

One more spec rule shows up on the Kubernetes page: healthy rows are quiet. A `Running` pod's badge is drawn in neutral blue-grey; only `ImagePullBackOff` gets red. Your eye goes to the one thing that needs it.

### 5.3 Type

Two fonts, bundled with the app (no font CDN): **Archivo** for prose and headings, **JetBrains Mono** for anything that is an identifier, a time or a label. Pod names, tool IDs, UIDs, trace IDs and timestamps are always mono. Two helper classes carry the spec's label style: `.vy-label` (11px, uppercase, wide tracking) and `.vy-micro` (10px).

---

## 6. A tour of the files

```
frontend/src/
  main.tsx                    starts React
  App.tsx                     router + Refine + the shell (sidebar and main)
  dataProvider.ts             the only fetch()
  index.css                   tokens, fonts, page background
  lib/
    status.ts                 tones: glyph, text colour, tint
    api-health.ts             useApiHealth
    agent.ts                  types for evidence and chat; useAgentStatus, useAsk
    pods.ts                   usePods; podTone (how a pod row is coloured)
  components/ui/              shadcn components (yours to edit)
  components/vyom/            Vyom's own components, named after the spec
    sidebar.tsx               logo, navigation, API status card
    ticker.tsx                the status line at the top of a page
    section-label.tsx         "00 / FLIGHT STATUS"
    status-text.tsx           glyph + label in a tone
    status-badge.tsx          the tinted badge used in tables
    pipeline-strip.tsx        the five-cell strip
    ask-vyom.tsx              the agent panel: form on the left
    answer.tsx                …answer, citations and evidence on the right
  pages/
    today.tsx                 "/"            ticker, headline, Ask Vyom, strip
    kubernetes.tsx            "/kubernetes"  ticker with counts, pods table
```

### 6.1 Follow one render: the Kubernetes page

1. `App.tsx` matches `/kubernetes` and renders `<Kubernetes />`.
2. `usePods()` fires `GET /api/kubernetes/pods` and returns `pending: true`. The page shows "Reading pods…".
3. The response arrives. React calls `Kubernetes()` again, now with `view.evidence`.
4. The ticker counts rows by tone with `podTone` (`Running` and all containers ready → ok; `Pending` → caution; anything else → alert).
5. The chips above the table are read straight from the evidence: `direct · kubernetes-pods`, `kind-vyom / ns demo`, `● complete`, `2 pods`. These are guide 3's `source.path`, `source.collector`, `source.connection_id`, `state`, `coverage.returned`.
6. The table maps `evidence.items` to rows.
7. Fifteen seconds later the hook fetches again and steps 3–6 repeat.

Then read the branches in the same file for the other states: not configured, `denied`/`missing` (errors listed, no table), `zero` ("The read completed and found no pods"), `partial`, and the stale alert. Each backend state from guide 3, section 5.2 has a visible counterpart.

### 6.2 Follow one click: asking a question

1. You type; `question` is local state in `ask-vyom.tsx` (`useState`).
2. Enter or the button calls `chat.ask(question.trim())`. `chat` comes from `useAsk()` in `today.tsx`, one level up, because the strip and the ticker also need the result.
3. While `chat.pending`, the button reads "Asking…" and the right column says what is happening.
4. The result arrives. `answer.tsx` renders one of three things: the answer with citations, a tinted box with the outcome and limitation, or a "did not reach the agent" error if the HTTP request itself failed.
5. `CitedText` splits the answer on `[n]` and draws each as a small superscript in the agent colour, with the cited pod's name as a tooltip. The same number appears beside that pod in the evidence list below: that is how you check a claim by eye.

### 6.3 Why some sidebar entries are not links

`sidebar.tsx` lists surfaces in delivery order. An entry with a `to` is a real route (Today, Kubernetes). An entry with only a `sprint` (AWS · S2, Findings · S4 …) is drawn dim, is not a link, and has no page. They show where the console is going without a placeholder page pretending something exists. `docs/design/DESIGN.md` §0 has the full mapping of surface to sprint, and the list of things in the mockups that are outside the 12-week plan.

---

## 7. What is not there, on purpose or not yet

- **No tests for the UI.** `npm run typecheck`, `npm run lint` and `npm run build` are the automated checks. The pages were verified by driving a headless browser and reading the screen, which is a manual check, not a regression test.
- **No login.** S6. Until then the app is reached on localhost only.
- **No history.** Reload the page and the last answer is gone; chat history is S3.
- **No Markdown rendering.** The answer is shown as plain text. The model is asked to write plain text.
- **No streaming.** The answer appears when it is complete.
- **Static sprint labels.** The "S2", "S4" tags and the "not built" strip cells are text in the source, not read from the backend. They need editing when those surfaces land.
- **Keyboard and screen-reader behaviour was written for but not tested**: real buttons and links, labels, `aria-current`, `aria-live` on the answer column, glyphs beside colours.

---

## 8. Say it back

<details><summary>1. Someone says "the frontend enforces that you only see the demo namespace". Correct them.</summary>

The frontend enforces nothing. It displays the namespace the backend reports and sends only a question. The limit is the trusted context on the server, the host's scope check, and Kubernetes RBAC. A person who replaces the UI with `curl` has exactly the same access.
</details>

<details><summary>2. Before any question is asked, why are the model and MCP cells not green?</summary>

Because the only thing known is that they are configured. `GET /api/agent` reads the operator file; it contacts nothing. Green would claim they work. The hollow glyph means "not reported". After a question, the cells take their tone from what really happened.
</details>

<details><summary>3. The backend is stopped while the Kubernetes page is open. Describe the next 20 seconds on screen, and where each piece comes from.</summary>

Within 10 seconds the sidebar card turns to "API UNREACHABLE" (`useApiHealth`). Within 15 seconds `usePods` fails; TanStack Query keeps the last data, so the table stays, the state chip becomes "stale", and an alert says the pods could not be fetched and gives the time of the last read. The "502" in the message is Vite's proxy failing to connect.
</details>

<details><summary>4. How would you change the alert red across the whole app, and why is it one edit?</summary>

Change `--vy-alert` in `frontend/src/index.css`. Components refer to the token through Tailwind classes such as `text-vy-alert`, and shadcn's `--destructive` is mapped to the same variable. No component contains a hex value.
</details>

<details><summary>5. Where would a bug live if the UI showed a pod as healthy when the evidence said <code>CrashLoopBackOff</code>?</summary>

In `podTone` in `lib/pods.ts`, the one function that turns a status string into a tone. The status text itself is printed unchanged from the evidence, so the words would still be right; only the colour and glyph would be wrong. That separation is deliberate: the UI's interpretation is small and in one place, and the raw value is always next to it.
</details>

<details><summary>6. The backend renames <code>collected_at</code> to <code>collectedAt</code>. What breaks, and what does not warn you?</summary>

The times in the UI become "Invalid Date" or blank. Nothing warns you: the frontend's `Evidence` type is written by hand and still says `collected_at`, so TypeScript is satisfied, and there are no UI tests. The backend tests pass. This is the cost of hand-written mirror types.
</details>

---

## 9. Try it

With the app running (see [README](README.md#run-the-app)):

- Open the browser's developer tools, Network tab, filter on `api`. Watch the three polls tick: `health` every 10 s, `pods` every 15 s, `agent` every 30 s. Ask a question and find the single `chat` POST; look at its request body (one field) and its response.
- In `frontend/src/index.css`, change `--vy-alert` to `#FF00FF` and save. The page updates without a reload. Change it back.
- In `frontend/src/lib/pods.ts`, make `podTone` return `'ok'` for everything and look at the Kubernetes page: the words still say `ImagePullBackOff`, the colour lies. Restore it.
- Stop `dev-up.sh` and watch both pages degrade. Start it again and watch them recover without a reload.
- Run the checks the CI runs:

  ```sh
  cd frontend && npm run typecheck && npm run lint && npm run build
  ```
