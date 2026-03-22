# Elara.ai — AI Patient Assistant

A full-stack AI medical assistant that helps patients schedule appointments, manage prescriptions, and get practice information through natural conversation with one-click voice handoff.

Built in 4 days. Under $7 total infrastructure cost.

**[Live Demo](https://elara-ai-frontend-5hst.vercel.app)** · **[API](https://api.elara-ai.quest)**

---

## What It Does

- **Smart Scheduling** — Matches body part to the right specialist, filters by day/time preference, books the appointment
- **Natural Conversation** — Patients provide details naturally ("I'm John Smith, 9296694178, john@gmail.com") and the LLM extracts everything at once
- **Mid-Flow Q&A** — Ask "what should I bring?" while booking and get a real answer, not "invalid input"
- **Post-Booking Guidance** — Personalized prep tips based on specialty and body part
- **Voice Handoff** — One click to continue the conversation as a phone call, full context preserved
- **Email Confirmations** — Sent from a custom domain via Resend
- **Prescription Refills** — Guided medication and pharmacy collection
- **Practice Info** — Hours, address, contact details
- **Safety** — No medical advice, no diagnosis, validated inputs, graceful degradation

---

## Architecture


**Why the proxy?** Vercel forces HTTPS. EC2 runs HTTP on a bare IP. Browsers block that combination (Mixed Content). A single Next.js API route proxies requests server-side — zero backend changes needed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | FastAPI, Python, Pydantic |
| LLM | Google Gemini 2.5 Flash Lite |
| Hosting | Docker on AWS EC2 |
| HTTPS | Cloudflare Tunnel (free, auto-certs) |
| Voice | VAPI |
| Email | Resend + custom domain |
| Deploy | Vercel (frontend), Docker Hub (backend) |

---

## LLM Design

Four Gemini functions, each with a specific purpose and a fallback if AI is unavailable:

| Function | What It Does | Fallback |
|----------|-------------|----------|
| Intent Extraction | Routes patient to the right workflow | Keyword matching |
| Reply Polish | Makes responses sound human | Original template |
| Multi-Field Intake | Parses name, DOB, phone, email from one message | One-at-a-time prompts |
| Booking Guidance | Personalized prep tips after confirmation | Skipped gracefully |

Cost: ~$0.07 per 1,000 conversations — 7x cheaper than GPT-4o.

---

## Providers

| Doctor | Specialty | Treats |
|--------|----------|--------|
| Dr. Sarah Chen | Orthopedics | Knee, leg, ankle |
| Dr. Michael Rivera | Spine Care | Back, neck, spine |
| Dr. Emily Patel | Sports Medicine | Shoulder, arm, elbow, wrist |
| Dr. James Wilson | Dermatology | Skin, rash, scalp |

Unsupported concerns (eye, dental, ear) are explicitly rejected with a helpful message.

---

## Quick Start

**Frontend:**
```bash
npm install && npm run dev
```
**Backend:**
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

---

## Design Principles

- Graceful Degradation — Every LLM call has a fallback. App works without AI.
- Production Thinking — HTTPS everywhere. Input validation. No medical advice.
- Cost Efficiency — Under $7 total. Pennies per 1,000 conversations.
- Scalability Path — Docker to ECS. In-memory to Redis. EC2 to ALB. No rewrite needed.
