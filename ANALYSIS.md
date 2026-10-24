# Elara.ai — Analysis

Analysis only; no application code was changed. Line numbers refer to `main` @ `53186f9`.
Where I could not verify something from the repos (Vercel/Fly dashboards, Fly secrets) it is marked **(unverified)**.

## 1. Summary

* **Bug 1 is client-side persistence, not caching.** `ChatShell` restores the session id and the whole transcript from `localStorage` on every load, with no expiry (`ChatShell.tsx:103-114`). When Fly stops the machine, the in-memory `SESSION_STORE` is wiped, so that restored id then yields `404 Session not found` and the user is stuck until they press "New chat".
* **Bug 2 and Bug 1 are one problem.** `fly.toml` has `auto_stop_machines='stop'` and `min_machines_running=0`. I measured 4.7 s for the first health request and 0.13 s for the second. Each stop also destroys all state. The frontend has no timeout, retry, warm-up or "waking up" handling. Recommendation: `min_machines_running = 1` plus a small frontend recovery path (§5).
* **The request flow in the brief is out of date.** Since 2026-04-04 the browser calls Fly directly (`NEXT_PUBLIC_API_BASE_URL`); the Vercel proxy route is dead code that points at `api.elara-ai.quest`, which did not connect when I tested it. The README still describes EC2, Cloudflare Tunnel and the proxy, and says "four" Gemini functions where the code has five.
* **The two frontends are source-identical.** `frontend/` in the main repo and `Elara.ai_frontend` differ only by Docker files, boilerplate docs, and the unused proxy route. `main/frontend` can be the single source of truth and Vercel can be pointed at it with Root Directory = `frontend`.
* **For health-data roles the biggest gaps are:** no persistence (everything is a Python dict), no auth on endpoints that return PHI, PHI in prompts/logs/VAPI payloads with no redaction or audit trail, zero tests, no CI, and LLM timeouts that don't actually work because the Gemini call is synchronous inside `async def`.

## 2. Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md): request-flow diagram, endpoints, Pydantic models, session storage, state-machine diagram, the five Gemini functions with fallbacks, env vars, Dockerfile, `fly.toml` and Vercel notes.

## 3. Frontend repo diff

Compared `main/frontend` against a fresh clone of `github.com/AmaanIlahi/Elara.ai_frontend` @ `c6c32ee` (2026-04-04). The path you gave as `<vercel-frontend-repo>` was a placeholder; the older local copies under `E:\Projects\Kyron\Elara.ai\` are stale and have no GitHub remote for this repo, so I did not use them.

| Area | `main/frontend` | `Elara.ai_frontend` (Vercel) | Notes |
|---|---|---|---|
| **App source** (`app/`, `components/`, `lib/`, `public/`) | same | same | `diff -r` reports no difference in any file |
| `package.json`, `package-lock.json`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`, `.gitignore` | same | same | Next 16.2.0, React 19.2.4, Tailwind 4, no extra deps |
| `next.config.ts` | `output: "standalone"` | `output: "standalone"` | identical; see below |
| `lib/api.ts` base URL | `NEXT_PUBLIC_API_BASE_URL \|\| "http://localhost:8000"` | same | both call the backend directly |
| `app/api/schedule/route.ts` | present | present | legacy mock, unused |
| **`app/api/proxy/[...path]/route.ts`** | absent | **present** | POST-only passthrough to `BACKEND_URL \|\| https://api.elara-ai.quest`. Nothing calls it since `db23fb8`. |
| `Dockerfile`, `.dockerignore` | present | absent | leftover from the EC2 deployment (`ARG NEXT_PUBLIC_API_BASE_URL`, standalone output) |
| `elara-ai` | git **gitlink** (mode 160000 -> `841c362`) with no `.gitmodules` | absent | broken pseudo-submodule from a nested clone; checks out as an empty dir |
| `AGENTS.md`, `CLAUDE.md`, `README.md` | absent | present | `README.md` is the create-next-app boilerplate |
| `next-env.d.ts` | absent | present (tracked) | auto-generated |
| `.vs/slnx.sqlite` | absent (but `.vs/` is tracked at the repo root) | present (tracked) | IDE junk in both |
| **Env vars** | `NEXT_PUBLIC_API_BASE_URL` (api.ts, Dockerfile `ARG`) | `NEXT_PUBLIC_API_BASE_URL`, plus `BACKEND_URL` in the dead proxy | No `.env*` committed in either. Vercel dashboard values **(unverified)** |
| Vercel config | none | none (`vercel.json` absent) | Root directory/preset live only in the dashboard **(unverified)** |

**Source of truth:** `main/frontend`. The deploy repo has no code the main repo lacks, except the dead proxy. Its history is `main`'s history plus earlier proxy-era commits.

**Can they be merged into one repo?** Yes. Steps (not applied):
1. In the Vercel project, Settings -> Git: connect `AmaanIlahi/Elara.ai` and set **Root Directory = `frontend`** (framework preset Next.js).
2. Copy the env vars across; confirm `NEXT_PUBLIC_API_BASE_URL` is the `https://backend-purple-pine-3154.fly.dev` URL for Production **and** Preview.
3. Remove the stray `frontend/elara-ai` gitlink, then archive `Elara.ai_frontend`.
4. Decide on `output: "standalone"`. Vercel is not known to need it; it was removed once as "incompatible with Vercel" (`8b538e5`) and is present now while the site apparently deploys. Keep it only if you still build the Docker image.
5. Optional: set "Ignored Build Step" so backend-only commits don't trigger a frontend deploy.

Caveat: Preview deployments get new `*.vercel.app` hosts that are not in the backend CORS list, so previews will fail until CORS uses a regex or env-driven list.

## 4. Bug 1: stale conversation on load

### Findings by hypothesis

| Hypothesis | Result |
|---|---|
| localStorage / sessionStorage / cookies | **Confirmed cause.** localStorage holds three keys (`lib/session.ts:1-3`). No sessionStorage or cookies anywhere (grep over `app lib components`). |
| Hard-coded / reused `session_id` | No. `session_id` is only ever the value returned by the server (`ChatShell.tsx:155-158`) or the one restored from localStorage (`:112`, sent at `:149`). |
| Backend in-memory state keyed by something constant | No. `SESSION_STORE` is keyed by a server-generated uuid4 (`session_service.py:7-13`, `schemas/session.py`). It is process-global, but a fresh visit with no `session_id` gets a fresh session. The globals `BOOKED_SLOTS` and `REFILL_REQUESTS` are never shown in a conversation. |
| Next.js / Vercel / HTTP caching | **Ruled out.** The browser calls the backend with client-side `fetch` POSTs (never cached). The only route handlers (`api/schedule`, deploy-only `api/proxy`) are POST-only, which Next never caches statically. There is no `Cache-Control`, `revalidate`, `cache:` or `dynamic` setting anywhere (grep), and nothing in the backend sets cache headers. `page.tsx` is statically prerendered, but `ChatShell` returns `null` until hydrated (`:284`), so no conversation is baked into the HTML. |
| React init/effects restoring messages | **Confirmed cause**, same as the first row (the effect is the restore mechanism). |

### Root cause

`frontend/components/chat/ChatShell.tsx`

* **Lines 103-114** (mount effect) read `elara_chat_messages`, `elara_chat_meta` and `elara_session_id` from localStorage and put them straight into state.
* **Lines 116-117** write messages and meta back on every change, so the "previous conversation" is always the latest one, forever. There is no timestamp, TTL or version check.
* **Lines 86-100 and 300-310**: the 10-minute inactivity timer only shows a banner. It never clears storage, and a reload resets it.
* **Line 322**: "Continue on phone" is enabled whenever a `sessionId` exists, so after a reload it is live for the previous call/session. That is probably the "last call" you see.
* `handleReset` (`:273`) is the only path that calls `clearStoredChatState`.

### Second-order failure (the worse one)

`routes/chat.py:207-210` returns `404 "Session not found"` for any unknown `session_id`. After a Fly auto-stop, redeploy, or crash, the restored id is unknown. The frontend then shows the error text as a chat bubble (`ChatShell.tsx:234-243`) and keeps the dead id (`setStoredSessionId` is only called on success). Every later message fails identically until the user clicks "New chat". The visible transcript also disagrees with the server, which has forgotten the conversation.

If the server is still up, the old session resumes. If its `status` is `completed` (after BOOKED or REFILL_SUBMITTED), `chat.py:215-216` silently makes a new session while the UI still shows the old booking cards.

### Proposed fix (not applied)

1. **Decide the product rule**, then enforce it in the mount effect. Simplest: treat a page load as a new conversation. Don't restore from storage, or move storage to `sessionStorage` so only an in-tab refresh keeps the chat. If you want resume-on-refresh, store `{savedAt}` with the data and discard anything older than N minutes (reuse the existing 10-minute constant).
2. **Recover from 404.** In `sendChatMessage`/`handleSend`, on a 404 `Session not found`: call `clearStoredChatState()`, reset state, and retry once with `session_id: null`. Show a one-line "Your previous session expired, starting a new one" note.
3. **Gate "Continue on phone"** on a session confirmed alive in this page load (e.g. set only after the first successful `/chat` response).
4. **Backend (belt and braces):** on an unknown `session_id`, create a new session and return it rather than 404, or return a typed error code the client can match on. Long term, persist sessions (§6) so a restart doesn't orphan clients.
5. Add `export const dynamic = "force-dynamic"` to the proxy/schedule route handlers only if they stay; they are not part of this bug.

## 5. Bug 2: Fly.io cold starts

### What the code and config say

| Item | Value |
|---|---|
| `auto_stop_machines` | `'stop'` |
| `auto_start_machines` | `true` |
| `min_machines_running` | `0` |
| VM | 1 shared CPU, 1 GB, region `ewr` |
| Health endpoint | exists at **`/api/v1/health`** (static JSON). There is no `/health` and no Fly `[[http_service.checks]]`. |
| Startup work | imports FastAPI, slowapi, `google.genai`, httpx/requests, builds **two** `genai.Client`s at import (`NLUService()` and `LLMService()` in `chat.py:44-45`), generates provider slots, and prints a startup line. No model download or DB connection. |
| Measured (my curl, 2026-10-24) | first request to `…fly.dev/api/v1/health`: **4.72 s** total (TTFB 4.72 s). Immediately after: **0.13 s**. `api.elara-ai.quest` did not connect. |
| Frontend handling | `fetch` with no `AbortController`/timeout, no retry, no warm-up call, no "waking up" message. A failure shows the raw `error.message` (e.g. "Failed to fetch") as a chat bubble (`ChatShell.tsx:234-243`). |

Fly's proxy normally holds the first request until the machine boots, so the usual symptom is a ~5 s stall rather than a failure; slower boots or a client giving up produce the "failed" case. The larger cost is that **stopping the machine erases `SESSION_STORE`, `BOOKED_SLOTS` and `REFILL_REQUESTS`**, which triggers Bug 1's 404. How many machines `fly deploy` created is **(unverified)**; with two machines in-memory sessions would also break across them.

### Options (prices are approximate list prices from memory; confirm on fly.io/docs/about/pricing)

| Option | Pros | Cons | Rough cost |
|---|---|---|---|
| **a) `min_machines_running = 1`** | One-line change. Removes cold starts. Sessions survive idle periods (not deploys/crashes). | Pays for 24/7 uptime; still loses state on deploy/restart; single point of failure. | shared-cpu-1x 1 GB: about **$5-6 / month** |
| **b) Scheduled ping** (GitHub Actions / Vercel cron on `/api/v1/health`) | Cheap if the schedule is sparse. | GitHub cron is best-effort with a 5-minute minimum and delays, and scheduled workflows are paused after 60 days of repo inactivity. Pings frequent enough to avoid auto-stop make the machine effectively always-on, i.e. the cost of (a) with more moving parts. Vercel Hobby cron is limited to daily. Doesn't help state loss on restart. | $0 for the pinger; machine hours if it keeps it awake |
| **c) Frontend warm-up on load + retry/backoff** | Free. Fixes the UX: user types while the machine boots. Add a "waking up" hint and a 404-recovery path and it also fixes Bug 1's stuck state. | First visitor still waits ~5 s; doesn't remove state loss; extra request per page view. | $0 (stopped machine costs only storage) |
| **d) Combination (a + c)** | No cold start for normal traffic, plus resilience when the machine does restart (deploys, crashes). | Same monthly cost as (a). | about $5-6 / month |

### Recommendation

**(d) = (a) + (c).** Set `min_machines_running = 1` (and keep exactly one machine while sessions are in memory), add a Fly HTTP check on `/api/v1/health`, and ship the frontend pieces: fire a no-body `GET /api/v1/health` on mount, wrap `fetch` with a timeout plus 2-3 retries with exponential backoff on network errors/502/503, show "Waking up the assistant…" after ~2 s, and implement the §4 404 recovery. If you want to stay at ~$0 for a portfolio demo, choose **(c) alone**, accepting a ~5 s first load. Skip (b).

## 6. Upgrade roadmap

Ranked by impact for backend / AI-engineering applications at health-data companies. Only gaps verified in the code are listed; "evidence" says what exists today.

| # | Item | Evidence in repo today | Why it matters for health data roles | Effort | Priority |
|---|---|---|---|---|---|
| 1 | **Persistent storage** (Postgres, plus Redis or a TTL column for sessions): sessions, appointments, refill requests, audit log; remove `BOOKED_SLOTS`/`REFILL_REQUESTS` globals | Everything is Python dicts (`SESSION_STORE`, `BOOKED_SLOTS`, `REFILL_REQUESTS`); bookings vanish on restart; `sqlalchemy`/`alembic` are already in `requirements.txt` but never imported | Without durable, queryable records there is no "system of record" story. It also fixes Bug 1's root, enables a unique constraint on (provider, slot) to stop double-booking, and lets you show migrations and transactions | M | **P0** |
| 2 | **Tests + CI** (pytest for `intake_service`, scheduling parsers, `NLUService` fallback, chat state transitions with a stubbed `LLMService`; GitHub Actions: lint, test, build, then `fly deploy` and Vercel) | No test files, no `.github/`, no pytest in requirements; deploy by hand **(unverified)** | Table stakes for regulated software; also the easiest way to prove the state machine and fallbacks work | M | **P0** |
| 3 | **PHI handling + audit trail**: stop logging email/response bodies, redact before prompts, minimise what goes to Gemini/VAPI, add an append-only access/audit log, auth on session endpoints | PHI-bearing: Resend config/body printed (`email_service.py:544-566`); last 8 turns including typed name/DOB/phone/email go to Gemini (`_format_history`, `llm_service.py:374`); VAPI system prompt embeds the whole `collected_data` (`voice_prompt.py:14`) and goes to OpenAI via VAPI; `GET /session/{id}` returns everything with no auth; `/voice/webhook` has no signature check; `DEBUG` defaults to True | HIPAA-style thinking (minimum necessary, BAAs, auditability) is the first thing a health-data interviewer probes. A redaction layer plus a documented data-flow diagram is a strong portfolio piece | M | **P0** |
| 4 | **Structured extraction reliability**: Pydantic schema for `extract_intake_fields` (currently free JSON), retries with backoff, log schema failures, and a labelled eval set with accuracy/F1 per field and per intent, run in CI | Only function 1 uses `response_schema`; function 3 `json.loads` an unconstrained dict then regex re-validates; errors swallowed by bare `except`; **no eval data or accuracy numbers exist**; the README's "$0.07 per 1,000 conversations" has no token accounting behind it | "Show me your eval numbers" is the central AI-engineering question. This converts the project from demo to measured system | M | **P0** |
| 5 | **Fix the LLM concurrency/timeout bug**: use `client.aio.models.generate_content` (or `asyncio.to_thread`), enforce `llm_timeout_seconds`, add retry with jitter | Sync call inside `async def` blocks the loop; `asyncio.wait_for` cannot cancel it; `llm_timeout_seconds` unused | Real correctness and latency bug; a concrete thing to point to in a review | S | **P0** |
| 6 | **Observability**: structured JSON logs, request-ID middleware, per-call LLM latency and token counts (cost per conversation), health/readiness with a dependency check | 22 bare `print()`s plus a request/response print; `latency_ms` computed and dropped (`llm_service.py:117`) | Needed for the cost claims and for debugging fallbacks (today a Gemini failure is silent). Directly answers "how would you monitor this?" | S-M | P1 |
| 7 | **FHIR-shaped domain model**: `Patient`, `Appointment`, `Slot`/`Schedule`, `MedicationRequest`, `Practitioner` as Pydantic models (e.g. `fhir.resources`) behind the services; use FHIR-style codes for status | Domain objects are untyped dicts inside `collected_data`; DOB/phone/email duplicated on `Session` and in `collected_data` | Signals interoperability literacy, which most health-data startups care about. Also cleans up the `collected_data` grab-bag | M | P1 |
| 8 | **Booking correctness**: re-check availability inside the confirm step, make it atomic (DB unique constraint), return a friendly conflict; fix the voice tool that overwrites `collected_data` | `confirm_booking_from_session_data` marks a slot booked without checking it is free (`scheduling_service.py:414-416`); `voice_tools.py:418-422, 441-444, 463-466` replace `collected_data` with only the metadata | Double-booking and data loss are the kind of defect that matters in clinical scheduling | S | P1 |
| 9 | **Security hardening**: verify VAPI webhook secret, per-session auth token (or signed session cookie), real rate limiting (one `Limiter`, `SlowAPIMiddleware`, `--proxy-headers`/`--forwarded-allow-ips` for Fly), env-driven CORS incl. previews, `DEBUG=False`, input length caps on `ChatRequest.message`, E.164 validation before `"+1"+phone`, `.dockerignore`, non-root container | Details under "Evidence" in ARCHITECTURE.md §5; email template inserts names only after a `[A-Za-z'-]` filter (OK), but `message` has no max length | Baseline expectations for anything touching PHI | M | P1 |
| 10 | **Frontend Bug 1/2 fixes** (§4, §5) | `ChatShell.tsx`, `lib/api.ts` | Needed for a clean demo link, but low backend depth | S | P1 (do first for the demo) |
| 11 | **Repo hygiene**: root `.gitignore` (tracked: `.vs/`, `__pycache__/*.pyc`), drop unused deps (`boto3, aiohttp, passlib, bcrypt, python-jose, …`), delete dead frontend code (`chat-engine.ts`, `mock-data.ts`, `api/schedule`, `/chat/stream` if unused), re-encode `requirements.txt` as UTF-8 and pin versions, remove `frontend/elara-ai` gitlink | See §3 and ARCHITECTURE.md §5.2 | First impression for reviewers who browse the repo | S | P2 |
| 12 | **DOB parsing ambiguity**: slash dates try `%d/%m/%Y` before `%m/%d/%Y`, so `03/04/1990` becomes 3 April for a US clinic | `intake_service.py:149-154` | A concrete, testable data-quality bug that a unit test would catch | S | P2 |
| 13 | **Replace keyword confirm/decline matching** (`"ok"` and `"no"` are substring tests, so "not sure" or "no thanks, yes" are mis-parsed) with intent classification plus a rule fallback | `chat.py:641-643, 1095-1097` | Improves safety of the irreversible steps | S-M | P2 |

## 7. Outdated docs / config

| Where | What is out of date | Should be |
|---|---|---|
| `README.md` "Architecture" | Diagram section is empty; text still says "EC2 runs HTTP on a bare IP… a single Next.js API route proxies requests" | Browser -> Fly.io HTTPS directly (CORS); proxy removed in `db23fb8` |
| `README.md` Tech Stack | "Docker on AWS EC2", "Cloudflare Tunnel", "Docker Hub" | Fly.io (`ewr`, built from `backend/Dockerfile` via `fly deploy`) |
| `README.md` Design Principles | "Docker to ECS… EC2 to ALB" | Fly machines |
| `README.md` "Four Gemini functions" | Table lists 4 | Code has **5**: add `generate_general_reply` (mid-flow Q&A and unknown intent) |
| `README.md` header | "**[API](https://api.elara-ai.quest)**" | That host did not connect on 2026-10-24. Use `https://backend-purple-pine-3154.fly.dev` or a new custom domain |
| `README.md` Quick Start | Omits env vars | Needs `LLM_ENABLED`, `GEMINI_API_KEY`, `VAPI_*`, `RESEND_*`, `PUBLIC_BACKEND_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL` |
| `README.md` cost claim | "$0.07 per 1,000 conversations", "under $7" | No token or cost tracking exists to substantiate it; Fly always-on would add about $5-6/month |
| `README.md` voice | Doesn't say the call model is OpenAI `gpt-4.1` (set in `voice_prompt.py:53`), not Gemini | Add |
| `backend/fly.toml` | `[processes]` command duplicates and overrides the Dockerfile CMD; `memory` and `memory_mb` both set; no health check | Pick one source for the start command; add `[[http_service.checks]]` on `/api/v1/health` |
| `backend/app/core/config.py` | `FRONTEND_ORIGIN`, `PUBLIC_FRONTEND_BASE_URL`, `LLM_TIMEOUT_SECONDS` are declared but unused; CORS is hard-coded in `main.py:36-41` | Drive CORS from env; remove dead settings |
| `backend/requirements.txt` | UTF-16; 9 unused dependencies; unpinned (`>=`) | UTF-8, pinned, trimmed |
| `deploy repo app/api/proxy/…` | Defaults to dead Cloudflare host; unused | Delete |
| `frontend/Dockerfile`, `.dockerignore` | EC2-era, unused on Vercel | Delete or document |
| `frontend/next.config.ts` | `output: "standalone"` only serves the Docker image | Remove if Docker is dropped |
| Both `.gitignore`s | Backend has none; root has none; `.vs/`, `*.pyc` tracked; `.env` and `*.pem` not ignored for the backend | Add root + backend ignore files |
| Local-only note | The old copy at `E:\Projects\Kyron\Elara.ai\` contains `backend/.env` and `fastapi-key.pem` on disk. They are not in this repo's git history, but `backend/` has no `.dockerignore`, so a `fly deploy` run from a folder holding a `.env` would bake it into the image | Add `.dockerignore`; rotate keys if that folder was ever shared |
| Code comment | `chat.py:9` and `main.py:9` each create their own `Limiter` | Single shared limiter |
| `chat.py:114` comment | Explains why polishing is disabled for `SCHEDULING_NEEDS_BODY_PART` (a loop). Fine, but a regression test is missing | Add test |

## 8. Open questions for me

1. What is `NEXT_PUBLIC_API_BASE_URL` set to in Vercel (Production and Preview)? If it is unset, the deployed site would target `localhost:8000`, so I assume it is the Fly URL.
2. Is `api.elara-ai.quest` retired, or is it a custom domain you intend to point at Fly? Should the README and the proxy default follow it?
3. Which Fly secrets are set? In particular `LLM_ENABLED=true`, `GEMINI_API_KEY`, `PUBLIC_BACKEND_BASE_URL` (the webhook URL given to VAPI), `VAPI_*` and `RESEND_*`. If `LLM_ENABLED` is missing, production runs only on keyword fallbacks.
4. How many Fly machines exist right now (`fly status`)? With more than one, in-memory sessions will break randomly across machines.
5. Is the Resend sender a verified domain, or still `onboarding@resend.dev`? On the sandbox sender, only the account owner receives mail, and the code reports success on a 403.
6. Desired page-load behaviour: always a fresh chat, or resume after a refresh (and for how long)? This decides the fix in §4.
7. Do you want one repo (Vercel Root Directory = `frontend`) and the `Elara.ai_frontend` repo archived?
8. Is the voice agent staying on OpenAI `gpt-4.1` via VAPI? That is a separate PHI processor from Gemini and matters for the data-flow story.
9. Which two or three upgrades do you want to feature for job applications? My suggestion: persistence + FHIR models, the eval harness with published accuracy numbers, and the PHI/audit layer, in that order.
