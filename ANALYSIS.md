# Elara.ai — Analysis

The first version of this analysis was written against `main` @ `53186f9` with no code changed. It has since been updated for **Phase 0** and **Phase 0.5**: findings that were fixed are marked **Done**, and what is left is marked **Open**. Where something cannot be verified from the repos (Vercel/Fly dashboards, Fly secrets) it is marked **(unverified)**.

## 1. Summary

* **Bug 1 (stale conversation) is fixed.** The chat now lives in `sessionStorage`, a `404 {"error":"session_expired"}` from the backend clears it and retries once with a new session, and "Continue on phone" only enables after a successful `/chat` in the current page load. *(Phase 0)*
* **Bug 2 (Fly cold starts) is mitigated, not removed.** The frontend warms the backend on load, retries with backoff, shows "Waking up the assistant…" and uses friendly errors; `fly.toml` has a `/api/v1/health` check. `min_machines_running` is still `0` by choice, so the first visit after idle still waits a few seconds and a stop still erases all in-memory state. *(Phase 0)*
* **The abuse and PHI surface is much smaller.** One shared rate limiter keyed on `Fly-Client-IP`, one voice call per session, US-phone validation, a VAPI webhook secret, a 1000-character message cap, and six unused endpoints (one of which returned a whole session including PHI) deleted. Email (Resend) is gone; a booked appointment is downloadable as an `.ics`. *(Phase 0.5)*
* **Correctness bugs from the analysis are fixed:** async Gemini calls with enforced timeouts, atomic slot claims, the voice tool that wiped `collected_data`, US-first DOB parsing with age checks, and strict yes/no matching at the book/submit steps. 163 backend tests cover them. *(Phase 0 and 0.5)*
* **Still open for health-data roles:** no persistence (everything is a Python dict), no auth beyond the unguessable `session_id`, PHI still goes into Gemini prompts and the VAPI system prompt with no redaction or audit trail, no CI, no eval numbers, and CORS still excludes Vercel preview URLs.

## 2. Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md): request-flow diagram, endpoints, Pydantic models, session storage, state-machine diagram, the five Gemini functions with fallbacks, env vars, Dockerfile, `fly.toml` and Vercel notes. It describes the code as of Phase 0.5.

## 3. Frontend repo diff

Compared `main/frontend` against a fresh clone of `github.com/AmaanIlahi/Elara.ai_frontend` @ `c6c32ee` (2026-04-04), **before Phase 0**. The path given as `<vercel-frontend-repo>` was a placeholder; the older local copies under `E:\Projects\Kyron\Elara.ai\` are stale, so I did not use them.

| Area | `main/frontend` | `Elara.ai_frontend` (Vercel) | Notes |
|---|---|---|---|
| **App source** (`app/`, `components/`, `lib/`, `public/`) | same *at the time* | same *at the time* | `diff -r` reported no difference before Phase 0. **They now differ**: Phase 0 and 0.5 changes exist only in `main/frontend`. |
| `package.json`, lockfile, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`, `.gitignore` | same | same | Next 16.2.0, React 19.2.4, Tailwind 4, no extra deps |
| `next.config.ts` | `output: "standalone"` | `output: "standalone"` | identical; see below |
| `app/api/schedule/route.ts` | **deleted** (Phase 0.5) | present | legacy mock, unused |
| **`app/api/proxy/[...path]/route.ts`** | absent | **present** | POST-only passthrough to `BACKEND_URL \|\| https://api.elara-ai.quest`; unused since `db23fb8` |
| `Dockerfile`, `.dockerignore` | present | absent | leftover from the EC2 deployment |
| `elara-ai` | gitlink **removed** (`f6041f9`) | absent | was a broken pseudo-submodule |
| `AGENTS.md`, `CLAUDE.md`, `README.md` | absent | present | `README.md` is the create-next-app boilerplate |
| **Env vars** | `NEXT_PUBLIC_API_BASE_URL` | `NEXT_PUBLIC_API_BASE_URL`, plus `BACKEND_URL` in the dead proxy | Vercel dashboard values **(unverified)** |
| Vercel config | none | none (`vercel.json` absent) | Root directory/preset live only in the dashboard **(unverified)** |

**Source of truth:** `main/frontend`. The deploy repo has no code the main repo lacks, except the dead proxy.

**Open:** Vercel still builds from `Elara.ai_frontend` unless the project has been re-pointed. To ship the Phase 0/0.5 frontend, either set the Vercel project's Git repo to `AmaanIlahi/Elara.ai` with **Root Directory = `frontend`** (then archive the other repo), or copy `frontend/` across. If you re-point it, confirm `NEXT_PUBLIC_API_BASE_URL` is the Fly URL for Production **and** Preview, and decide whether to keep `output: "standalone"` (only the Docker image needs it).

Caveat: Preview deployments get new `*.vercel.app` hosts that are not in the backend CORS list, so previews fail until CORS is regex- or env-driven.

## 4. Bug 1: stale conversation on load — **Done (Phase 0)**

### Root cause (as found)

`ChatShell` restored the session id and the whole transcript from `localStorage` on every load with no expiry, and the only way to clear it was "New chat". After a Fly stop or deploy the in-memory `SESSION_STORE` was empty, so the restored id produced `404 "Session not found"` and every later message failed until the user pressed "New chat". "Continue on phone" was enabled whenever a `sessionId` existed, which is probably the "last call" you saw. Next.js/Vercel/HTTP caching, a hard-coded session id and backend state keyed by a constant were ruled out.

### What changed

| Finding | Fix |
|---|---|
| localStorage persisted forever | `sessionStorage` (refresh keeps the chat, a new tab starts clean); old `localStorage` keys are cleared |
| Unknown `session_id` -> text 404 | `404 {"error":"session_expired"}`; the frontend clears stored state, retries once with `session_id: null` and shows "Your previous session expired, starting a new one." |
| "Continue on phone" live for a dead session | enabled only after a successful `/chat` response in this page load |

## 5. Bug 2: Fly.io cold starts — **Mitigated (Phase 0), min machines still 0**

| Item | Value |
|---|---|
| `auto_stop_machines` / `auto_start_machines` / `min_machines_running` | `'stop'` / `true` / `0` (unchanged) |
| VM | 1 shared CPU, 1 GB, region `ewr` |
| Health endpoint | `/api/v1/health`; a Fly check now polls it *(Phase 0)* |
| Measured before the fix (2026-10-24) | first request **4.72 s**, then **0.13 s** |
| Frontend | warm-up `GET /api/v1/health` on mount, 15 s timeout with 3 retries (500 ms, 1 s, 2 s) on network errors and 502/503, a "Waking up the assistant…" notice after 2 s, friendly error text instead of the raw `error.message` *(Phase 0)* |

Timed-out POSTs are not retried (the server may already have processed them) and the voice handoff never retries, so a flaky network cannot duplicate a chat turn or place a second phone call.

**Still true:** stopping the machine erases `SESSION_STORE`, `BOOKED_SLOTS` and `REFILL_REQUESTS`, and now also the calendar link of an earlier booking. The frontend recovers, but the data is gone.

### Options still on the table (prices are approximate list prices from memory; confirm on fly.io/docs/about/pricing)

| Option | Pros | Cons | Rough cost |
|---|---|---|---|
| **a) `min_machines_running = 1`** | One-line change. No cold starts. Sessions survive idle periods (not deploys/crashes). | Pays for 24/7 uptime; single point of failure. | about **$5-6 / month** |
| **b) Scheduled ping** | Cheap if sparse. | Best-effort schedulers, paused after inactivity; frequent enough pings equal option (a). | $0 for the pinger |
| **c) Frontend warm-up + retry** *(done)* | Free; fixes the UX. | First visitor still waits ~5 s; state still lost on stop. | $0 |
| **d) a + c** | No cold start for normal traffic plus resilience on restarts. | Same monthly cost as (a). | about $5-6 / month |

**Recommendation unchanged:** (d) for a live demo (`min_machines_running = 1`, exactly one machine while sessions are in memory); (c) alone if you want ~$0 and accept a ~5 s first load. Skip (b). Persisting sessions (roadmap #1) is the real fix for state loss.

## 6. Upgrade roadmap

Ranked by impact for backend / AI-engineering applications at health-data companies. "Status" reflects Phase 0 and 0.5.

| # | Item | Status | Why it matters for health data roles | Effort | Priority |
|---|---|---|---|---|---|
| 1 | **Persistent storage** (Postgres, plus Redis or a TTL column): sessions, appointments, refill requests, audit log; remove the `BOOKED_SLOTS`/`REFILL_REQUESTS` globals | **Open.** Still Python dicts. | A durable, queryable system of record; fixes the restart data loss; a unique constraint on (provider, slot) makes double-booking impossible across machines | M | **P0** |
| 2 | **Tests + CI** | **Partly done.** 163 pytest tests (state-machine pieces, booking race, voice merge, LLM timeouts, rate limits, webhook secret, calendar, DOB, confirm/decline). **No CI**, no frontend tests, no linters in a pipeline. | Table stakes for regulated software | M | **P0** |
| 3 | **PHI handling + audit trail** | **Partly done.** Removed `GET /session/{id}`, other unused PHI endpoints, the Resend body logging and `DEBUG=True`; webhook is authenticated; error bodies from VAPI are no longer echoed. **Open:** redaction before Gemini/VAPI prompts, minimum-necessary prompts, audit log, auth beyond the session id. | Minimum necessary, BAAs, auditability are the first thing a health-data interviewer probes | M | **P0** |
| 4 | **Structured extraction reliability**: schema for `extract_intake_fields`, retries, labelled eval set with accuracy/F1 | **Open.** No eval data or accuracy numbers exist. The README's cost claims were removed because nothing backed them. | "Show me your eval numbers" is the central AI-engineering question | M | **P0** |
| 5 | **LLM concurrency/timeout bug** | **Done (Phase 0).** Async client, enforced timeouts, one shared client, logging. No retries/jitter yet. | Real latency bug removed | S | P0 |
| 6 | **Observability**: structured logs, request IDs, LLM latency and token counts | **Open.** LLM failures are now logged and health is out of the request log, but there are no token counts, request IDs or JSON logs. | Needed for cost claims and debugging fallbacks | S-M | P1 |
| 7 | **FHIR-shaped domain model** | **Open.** | Interoperability literacy | M | P1 |
| 8 | **Booking correctness** | **Done (Phase 0).** Atomic claim with a friendly conflict message; voice tools merge instead of replacing `collected_data`. (Cross-machine safety still needs #1.) | Double-booking and data loss matter in clinical scheduling | S | P1 |
| 9 | **Security hardening** | **Mostly done.** Shared limiter on `Fly-Client-IP`, `/chat` 20/min, `/voice/handoff` 3/hour and one call per session, webhook secret, US-phone validation before `"+1"`, message cap, `DEBUG=False`, `.dockerignore`. **Open:** per-session auth token, env-driven CORS incl. previews, non-root container, limiter state is per process. | Baseline for anything touching PHI | M | P1 |
| 10 | **Frontend Bug 1/2 fixes** | **Done (Phase 0).** | Clean demo link | S | P1 |
| 11 | **Repo hygiene** | **Done** (root `.gitignore`, untracked `.vs/` and `*.pyc`, UTF-8 pinned `requirements.txt` without 9 unused packages, dead frontend code deleted, gitlink removed). **Open:** `frontend/Dockerfile` and `output: "standalone"` if Docker is dropped. | First impression for reviewers | S | P2 |
| 12 | **DOB parsing ambiguity** | **Done (Phase 0.5).** US-first, future dates and ages over 120 rejected, with tests. | A concrete data-quality bug | S | P2 |
| 13 | **Confirm/decline matching** | **Done (Phase 0.5).** `services/confirmation.py`: all words must be known yes/no words or fillers; "no thanks" and "not sure" re-ask. (No LLM classification; the rule set is deliberately closed and safe.) | Safety of the irreversible steps | S-M | P2 |
| 14 | **Appointment confirmation channel** | **Done (Phase 0.5).** Email via Resend replaced by a downloadable `.ics` built with the standard library. | Removes an external PHI processor and a mis-reported-success path | S | P2 |

## 7. Outdated docs / config

| Where | Status |
|---|---|
| `README.md` architecture, tech stack, Fly deploy, API link, five Gemini functions, voice model, Quick Start, cost claims | **Done** (Phase 0). |
| `README.md` "Email Confirmations", Resend in the stack, rate limits, webhook secret | **Done** (Phase 0.5). |
| `backend/fly.toml` health check, duplicate memory key | **Done** (Phase 0). The `[processes]` command still duplicates the Dockerfile `CMD`; harmless. |
| `backend/app/core/config.py` unused `FRONTEND_ORIGIN`, `PUBLIC_FRONTEND_BASE_URL` | **Done** (Phase 0.5). CORS origins are still hard-coded in `main.py` (**Open**, out of scope). |
| `backend/requirements.txt` UTF-16, unused and unpinned packages | **Done** (Phase 0.5). |
| Both `.gitignore`s, `.dockerignore`, tracked `.vs/` and `*.pyc` | **Done** (Phase 0). |
| Duplicate `Limiter` objects | **Done** (Phase 0.5): one limiter in `core/limiter.py`. |
| `deploy repo app/api/proxy/…` | **Open.** Dead code in `Elara.ai_frontend`; goes away when that repo is archived. |
| `frontend/Dockerfile`, `.dockerignore`, `next.config.ts` `standalone` | **Open.** EC2-era, unused on Vercel. |
| `chat.py` comment explaining why polishing is off for `SCHEDULING_NEEDS_BODY_PART` | **Open.** A regression test is still missing. |
| Local-only note: `E:\Projects\Kyron\Elara.ai\` holds a `.env` and `fastapi-key.pem` on disk | Not in this repo's history; `backend/.dockerignore` now keeps such files out of images. Rotate those keys if that folder was ever shared. |

## 8. Open questions for me

1. Which Fly secrets are set? After Phase 0.5 the backend needs `LLM_ENABLED=true`, `GEMINI_API_KEY`, `PUBLIC_BACKEND_BASE_URL`, `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID` and the new **`VAPI_WEBHOOK_SECRET`**. Without the last one, voice handoff returns 500 and every webhook call is rejected. `RESEND_*` can be unset.
2. How many Fly machines exist (`fly status`)? With more than one, in-memory sessions and rate-limit counters break randomly across machines.
3. Is `api.elara-ai.quest` retired, or a custom domain you intend to point at Fly?
4. Is the Vercel project still building from `Elara.ai_frontend`? If so none of the Phase 0/0.5 frontend work is live until it is re-pointed or the code is copied over.
5. Do you want `min_machines_running = 1` for the live demo (about $5-6/month), or keep scale-to-zero?
6. Is the voice agent staying on OpenAI `gpt-4.1` via VAPI? That is a separate PHI processor from Gemini and matters for the data-flow story.
7. Which two or three upgrades do you want to feature for job applications? Suggestion: persistence + FHIR models, the eval harness with published accuracy numbers, and the PHI redaction/audit layer, in that order.
