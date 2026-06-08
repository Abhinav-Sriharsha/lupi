# Lupi

Voice AI agent built on LiveKit, Groq, Deepgram, and Kokoro TTS.

## Structure

```
backend/
├── main.py              # FastAPI: token issuance + agent dispatch
├── kokoro_server.py     # Local Kokoro TTS streaming server (Apple Silicon)
├── requirements.txt
├── .env.example
├── agent/
│   └── lupi_agent.py    # LiveKit agent entrypoint
└── lupi/
    ├── prompts.py       # System prompts
    ├── tools.py         # Supabase-backed tools
    └── seed.py          # DB seed script
```

## Quickstart

```bash
cd backend
cp .env.example .env
# fill in .env values

pip install -r requirements.txt

# Start Kokoro TTS server (Apple Silicon)
python kokoro_server.py

# Start FastAPI
uvicorn main:app --reload --port 8000

# Start LiveKit agent
python -m agent.lupi_agent dev
```
