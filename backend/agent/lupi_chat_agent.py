import os
import json
import time
import asyncio
import aiohttp
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    Agent,
    AgentSession,
    TurnHandlingOptions,
)
from livekit.plugins import deepgram, silero
from livekit.plugins import openai as lk_openai
from openai import AsyncOpenAI

from kokoro_tts_plugin import KokoroTTS as KokoroTTSPlugin

import logging
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


SYSTEM_PROMPT = (
    "You are Lupi, a friendly voice AI assistant. "
    "Be casual, warm, and conversational. Keep responses under "
    "2 sentences. You're here to chat about anything."
)

GREETING = "Hey, I'm Lupi. What's on your mind?"


# ── Observability ──────────────────────────────────────────────────────────────

@dataclass
class TurnMetrics:
    turn: int
    transcript: str = ""
    response: str = ""
    ttft_ms: float = 0
    llm_ms: float = 0
    tts_first_chunk_ms: float = 0
    tts_total_ms: float = 0
    total_ms: float = 0


class SessionObserver:
    def __init__(self):
        self.turn_count = 0
        self.turns: list[TurnMetrics] = []
        self.current: TurnMetrics | None = None
        self.t_start: float = 0

    def on_user_speech(self, transcript: str):
        self.turn_count += 1
        self.t_start = time.perf_counter()
        self.current = TurnMetrics(turn=self.turn_count, transcript=transcript)
        self.turns.append(self.current)
        print(f"[TURN {self.turn_count}] User: {transcript}")

    def on_metrics(self, agent_metrics):
        if not self.current:
            return
        if hasattr(agent_metrics, "ttft") and agent_metrics.ttft:
            self.current.ttft_ms = round(agent_metrics.ttft * 1000)
            print(f"[LATENCY] TTFT: {self.current.ttft_ms}ms")
        if hasattr(agent_metrics, "inference_duration") and agent_metrics.inference_duration:
            self.current.llm_ms = round(agent_metrics.inference_duration * 1000)
            print(f"[LATENCY] LLM: {self.current.llm_ms}ms")
        if hasattr(agent_metrics, "duration") and agent_metrics.duration:
            self.current.tts_total_ms = round(agent_metrics.duration * 1000)
            print(f"[LATENCY] TTS: {self.current.tts_total_ms}ms")

    def on_agent_speech_committed(self, response: str):
        if self.current:
            self.current.total_ms = round((time.perf_counter() - self.t_start) * 1000)
            self.current.response = response
            print(f"[LATENCY] Total turn: {self.current.total_ms}ms")

    def print_summary(self):
        print(f"\n{'='*50}")
        print(f"SESSION SUMMARY — {self.turn_count} turns")
        if self.turns:
            totals = [t.total_ms for t in self.turns if t.total_ms > 0]
            ttfts  = [t.ttft_ms  for t in self.turns if t.ttft_ms  > 0]
            tts    = [t.tts_total_ms for t in self.turns if t.tts_total_ms > 0]
            ttfas  = [t.ttft_ms + t.tts_first_chunk_ms for t in self.turns if t.tts_first_chunk_ms > 0]
            if totals:
                print(f"Avg turn latency : {sum(totals)/len(totals):.0f}ms")
            if ttfts:
                print(f"Avg TTFT         : {sum(ttfts)/len(ttfts):.0f}ms")
            if tts:
                print(f"Avg TTS total    : {sum(tts)/len(tts):.0f}ms")
            if ttfas:
                print(f"Avg TTFA         : {sum(ttfas)/len(ttfas):.0f}ms")
        print(f"{'='*50}\n")


# ── Warmup ─────────────────────────────────────────────────────────────────────

async def warmup_pipeline(stt: deepgram.STT):
    print("[WARMUP] Pre-warming TTS and STT connections...")
    t_start = time.perf_counter()

    kokoro_url = os.getenv("KOKORO_URL", "http://127.0.0.1:8880")

    async def warm_tts():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{kokoro_url}/health") as resp:
                    data = await resp.json()
                    print(f"[WARMUP] Kokoro ready: {data}")
        except Exception as e:
            print(f"[WARMUP] Kokoro warmup failed (is kokoro_server.py running?): {e}")

    async def warm_stt():
        try:
            stream = stt.stream()
            silent_frame = rtc.AudioFrame(
                data=bytes(640),
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=320,
            )
            stream.push_frame(silent_frame)
            await stream.aclose()
            print("[WARMUP] Deepgram Nova-2 ready")
        except Exception as e:
            print(f"[WARMUP] STT warmup non-fatal: {e}")

    await asyncio.gather(warm_tts(), warm_stt())
    elapsed = round((time.perf_counter() - t_start) * 1000)
    print(f"[WARMUP] Both connections ready in {elapsed}ms")


# ── Entrypoint ─────────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    observer = SessionObserver()

    # ── Plugins ────────────────────────────────────────────────────────────────
    kokoro_url = os.getenv("KOKORO_URL", "http://127.0.0.1:8880")

    lupi_stt = deepgram.STT(
        model="nova-2",
        language="en-US",
        punctuate=True,
        smart_format=True,
    )
    lupi_tts = KokoroTTSPlugin(voice="af_sarah", speed=1.1, base_url=kokoro_url)
    print("[TTS] Using Kokoro local")

    def capture_kokoro_ttfc():
        """Read and reset Kokoro's first-chunk latency."""
        ttfc = lupi_tts.last_ttfc_ms
        lupi_tts.last_ttfc_ms = 0
        return ttfc
    lupi_vad = silero.VAD.load(
        min_speech_duration=0.1,
        min_silence_duration=0.5,
        prefix_padding_duration=0.2,
    )
    groq_client = AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    lupi_llm = lk_openai.LLM(client=groq_client, model="llama-3.3-70b-versatile")

    await warmup_pipeline(lupi_stt)

    # ── Agent ──────────────────────────────────────────────────────────────────

    agent = Agent(instructions=SYSTEM_PROMPT)

    session = AgentSession(
        stt=lupi_stt,
        vad=lupi_vad,
        llm=lupi_llm,
        tts=lupi_tts,
        turn_handling=TurnHandlingOptions(
            interruption={"enabled": True, "min_duration": 0.5, "min_words": 2},
            endpointing={"min_delay": 0.6},
        ),
    )

    # ── Metrics → frontend via data channel ────────────────────────────────────

    async def publish_turn_metrics(turn: TurnMetrics):
        payload = json.dumps({
            "type": "metrics",
            "turn": turn.turn,
            "ttft_ms": turn.ttft_ms,
            "tts_first_chunk_ms": turn.tts_first_chunk_ms,
            "tts_total_ms": turn.tts_total_ms,
            "ttfa_ms": turn.ttft_ms + turn.tts_first_chunk_ms,
            "total_ms": turn.total_ms,
        })
        try:
            await ctx.room.local_participant.publish_data(
                payload.encode("utf-8"), reliable=True
            )
            print(f"[METRICS] Published: {payload}")
        except Exception as e:
            print(f"[METRICS] Publish failed: {e}")

    # ── Hooks ──────────────────────────────────────────────────────────────────

    @session.on("user_input_transcribed")
    def on_user_speech(ev):
        if not ev.is_final:
            return
        observer.on_user_speech(ev.transcript)

    @session.on("conversation_item_added")
    def on_item_added(ev):
        msg = ev.item
        if hasattr(msg, "role") and msg.role == "assistant":
            response = msg.text_content or ""
            print(f"[AGENT]: {response}")
            if observer.current:
                observer.current.tts_first_chunk_ms = capture_kokoro_ttfc()
                print(f"[LATENCY] TTS first chunk: {observer.current.tts_first_chunk_ms}ms")
            observer.on_agent_speech_committed(response)
            if observer.current:
                asyncio.create_task(publish_turn_metrics(observer.current))

    @session.on("metrics_collected")
    def on_metrics(ev):
        observer.on_metrics(ev.metrics)

    # ── Start ──────────────────────────────────────────────────────────────────

    participant = await ctx.wait_for_participant()
    print(f"[LUPI-CHAT] Participant: {participant.identity}")

    await session.start(agent, room=ctx.room)

    try:
        print(f"[LUPI-CHAT] Greeting: {GREETING}")
        session.say(GREETING, allow_interruptions=True)
    except RuntimeError as e:
        print(f"[LUPI-CHAT] Session already closing, skipping greeting: {e}")

    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        print("[LUPI-CHAT] Session ended cleanly")
        observer.print_summary()


# ── Worker ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="lupi-chat",
    ))
