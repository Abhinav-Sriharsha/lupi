from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os, time
from livekit import api

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_AGENTS = {"lupi-agent", "lupi-chat"}

class TokenRequest(BaseModel):
    phone: str
    customer_name: str = ""
    agent_name: str = "lupi-agent"

@app.post("/token")
async def get_token(req: TokenRequest):
    if req.agent_name not in VALID_AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {req.agent_name}")
    room_name = f"lupi-{int(time.time())}"
    token = (
        api.AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET"))
        .with_identity(req.phone)
        .with_name(req.customer_name or req.phone)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    lk_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )
    await lk_api.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            room=room_name,
            agent_name=req.agent_name,
            metadata=req.phone,
        )
    )
    await lk_api.aclose()

    return {"token": token, "room": room_name, "livekit_url": os.getenv("LIVEKIT_URL")}

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "lupi"}
