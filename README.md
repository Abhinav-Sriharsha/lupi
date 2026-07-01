# Lupi — Real-time Voice Support Agent

A production-grade voice support agent for food delivery. Handles refunds, missing orders, and delivery issues end-to-end without human intervention.

## What it does

Lupi is a real-time voice agent backed by a 16-table production database with seeded customer scenarios, orders, dashers, and payment methods. When a customer calls and reports a late delivery, Lupi queries the database, calculates the delay, determines refund eligibility using a pure Python policy engine, and issues the refund to the correct payment method — all within a single phone call.

The key architectural decision: the LLM only generates speech. Every routing decision, tool call, and refund calculation is deterministic Python code.

## Architecture

```
Customer speaks
  → Deepgram Nova-2 (STT, real-time)
  → Silero VAD (end-of-speech detection)
  → FSM Orchestration Layer (6 stages, deterministic)
       ├── Intent Classifier (Groq 8B, parallel, ~250ms)
       ├── Tool Execution (Supabase, direct Python calls)
       └── Refund Policy Engine (pure Python, no LLM)
  → Groq Llama 3.3 70B (speech generation only)
  → Kokoro-82M TTS (sentence streaming)
  → LiveKit WebRTC (voice transport)
  → Customer hears response
```

### The parallel classifier

When the customer describes their issue, two things fire simultaneously:
- The 70B model generates a filler response ("Sorry to hear that, let me help")
- The 8B classifier returns the issue category in ~250ms

By the time the filler plays, the classifier has returned and database tools have already fired. This is why complex resolutions complete in under 4 seconds.

### The refund policy engine

Pure Python function. No LLM. No database call. Takes issue type, order details, and order status as input. Returns eligibility, refund type, and amount. Recalculates `minutes_late` from raw ISO timestamps — does not trust the database field.

```python
# Examples
late_delivery + minutes_late > 30  → partial refund (delivery_fee + service_fee)
missing_items                      → full refund (order total)
order_not_arrived                  → full refund (order total)
still_preparing                    → skip resolution, give ETA
```

## FSM Stages

```
INTRO
  ↓ customer responds
PHONE_COLLECTION     ← digit accumulation in code, not LLM
  ↓ 10 digits collected
ISSUE_COLLECTION     ← 8B classifier fires on customer speech
  ↓ issue classified
INVESTIGATION        ← parallel DB tool calls, refund policy runs
  ↓ eligibility determined
RESOLUTION           ← human-sounding response built from structured data
  ↓ refund or ticket issued
CLOSING              ← LLM handles free conversation, grounded to session context
```

## Stack

| Component | Technology |
|---|---|
| Voice transport | LiveKit WebRTC |
| STT | Deepgram Nova-2 |
| VAD | Silero |
| Main LLM | Groq Llama 3.3 70B |
| Intent classifier | Groq Llama 3.1 8B |
| TTS (local) | Kokoro-82M MLX (Apple Silicon) |
| TTS (production) | Kokoro-82M CPU (Railway) |
| Database | Supabase PostgreSQL (16 tables) |
| Backend | FastAPI |
| Frontend | React + TypeScript + Vite |
| Deployment | Railway (backend) + Vercel (frontend) |

## Latency

| Metric | Local (Apple Silicon MLX) | Production (Railway CPU) |
|---|---|---|
| TTFT avg | 193ms | 197ms |
| TTFA avg | 455ms | 527ms |
| Intent classification | 246ms | 318ms |
| TTS first chunk | 150–300ms | 400–800ms |

TTFA = Time to First Audio (from end of customer speech to first audio byte played).

## Demo Scenarios

Eight seeded scenarios in the database. Use these phone numbers when prompted:

| Phone | Customer | Scenario |
|---|---|---|
| (415) 555-0101 | Maya Patel | Late delivery — Chipotle, 50 min late |
| (415) 555-0102 | Jordan Rivera | Missing items — Shake Shack |
| (415) 555-0103 | Priya Sharma | Order never arrived — Din Tai Fung |
| (415) 555-0104 | Marcus Johnson | Still preparing — Sweetgreen |
| (415) 555-0105 | Aisha Williams | Restaurant cancelled — Halal Guys |
| (415) 555-0106 | Kevin Zhang | Happy path — Philz Coffee |
| (415) 555-0107 | Sofia Reyes | Wrong items — Curry Up Now |
| (415) 555-0108 | Eli Cohen | Food quality — Mendocino Farms |

## Running Locally

**Prerequisites:** Python 3.11+, Node 18+, Apple Silicon Mac (for Kokoro MLX)

```bash
git clone https://github.com/Abhinav-Sriharsha/lupi.git
cd lupi
cp backend/.env.example backend/.env
# Fill in API keys: LIVEKIT, DEEPGRAM, GROQ, SUPABASE
```

**Terminal 1 — Kokoro TTS server:**
```bash
cd backend
/path/to/kokoro-venv/bin/python kokoro_server.py
```

**Terminal 2 — FastAPI:**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 3 — Agent worker:**
```bash
cd backend
python agent/lupi_agent.py dev
```

**Terminal 4 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

## Project Structure

```
lupi/
├── backend/
│   ├── agent/
│   │   ├── lupi_agent.py          # Main support agent + FSM orchestration
│   │   └── lupi_chat_agent.py     # Free conversation agent
│   ├── lupi/
│   │   ├── fsm.py                 # 6-stage FSM + refund policy engine
│   │   ├── classifier.py          # Intent classifier (8B)
│   │   ├── tools.py               # Supabase tool functions
│   │   └── seed.py                # Database seeder (16 tables)
│   ├── kokoro_server.py           # Local TTS server (MLX)
│   ├── resemble_tts_plugin.py     # Resemble AI TTS plugin
│   └── main.py                    # FastAPI token endpoint
├── frontend/
│   └── src/
│       ├── App.tsx                # Landing page with dual orb demo
│       └── components/ui/
│           └── voice-orb.tsx      # WebGL2 animated orb
└── kokoro_deploy/
    ├── kokoro_server_linux.py     # Linux-compatible Kokoro for Railway
    └── Dockerfile
```
