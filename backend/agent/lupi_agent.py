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
from livekit.agents import llm as lk_llm
from livekit.plugins import deepgram, silero
from livekit.plugins import openai as lk_openai
from openai import AsyncOpenAI

from kokoro_tts_plugin import KokoroTTS as KokoroTTSPlugin
from resemble_tts_plugin import ResembleTTS
from lupi.classifier import classify_issue
from lupi.fsm import LupiFSM, LupiStage, STAGE_TOOLS
from lupi.tools import (
    get_customer_context,
    get_order_details,
    get_order_status,
    issue_refund,
    create_support_ticket,
    get_dasher_location,
)

import logging
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


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
        self._tts_seen: bool = False

    def on_user_speech(self, transcript: str):
        self.turn_count += 1
        self.t_start = time.perf_counter()
        self._tts_seen = False
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
            tts_val = round(agent_metrics.duration * 1000)
            if not self._tts_seen:
                self.current.tts_first_chunk_ms = tts_val
                self._tts_seen = True
                print(f"[LATENCY] TTS first chunk: {tts_val}ms")
            else:
                self.current.tts_total_ms = tts_val
                print(f"[LATENCY] TTS total: {tts_val}ms")

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
                print(f"Best turn        : {min(totals):.0f}ms")
                print(f"Worst turn       : {max(totals):.0f}ms")
            if ttfts:
                print(f"Avg TTFT         : {sum(ttfts)/len(ttfts):.0f}ms")
                print(f"Best TTFT        : {min(ttfts):.0f}ms")
            if tts:
                print(f"Avg TTS total    : {sum(tts)/len(tts):.0f}ms")
                print(f"Best TTS total   : {min(tts):.0f}ms")
            if ttfas:
                print(f"Avg TTFA         : {sum(ttfas)/len(ttfas):.0f}ms")
            print(f"{'─'*50}")
            for t in self.turns:
                print(f"  Turn {t.turn}: total={t.total_ms}ms ttft={t.ttft_ms}ms tts={t.tts_total_ms}ms ttfa={t.ttft_ms + t.tts_first_chunk_ms}ms")
                print(f"    User : {t.transcript[:80]}")
                print(f"    Agent: {t.response[:80]}")
        print(f"{'='*50}\n")


# ── Warmup ─────────────────────────────────────────────────────────────────────

async def warmup_pipeline(stt: deepgram.STT):
    print("[WARMUP] Pre-warming TTS and STT connections...")
    t_start = time.perf_counter()

    kokoro_url = os.getenv("KOKORO_URL", "http://127.0.0.1:8880")

    async def warm_tts():
        if os.getenv("USE_RESEMBLE", "false").lower() == "true":
            print("[WARMUP] Skipping Kokoro warmup (USE_RESEMBLE=true)")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{kokoro_url}/health",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"[WARMUP] Kokoro ready: {data}")
                    else:
                        print(f"[WARMUP] Kokoro warmup failed: status {resp.status}, continuing without warmup")
        except Exception as e:
            print(f"[WARMUP] Kokoro not available: {e}, continuing without warmup")

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


# ── Context helpers ────────────────────────────────────────────────────────────

def _build_context_block(ctx: dict) -> str:
    if not ctx or ctx.get("error"):
        return "\n\nCURRENT CALLER: Unknown — ask for their phone number first."

    orders = ctx.get("recent_orders") or []
    order_lines = []
    for o in orders:
        order_lines.append(
            f"  • {o['order_number']} — {o['restaurant']} — {o['status']} — ${o['total']}"
        )
    orders_text = "\n".join(order_lines) if order_lines else "  • No recent orders."

    pm = ctx.get("payment_method") or {}
    if pm.get("brand") and pm.get("last_four"):
        pm_str = f"{pm['brand']} ending {pm['last_four']}"
    elif pm.get("brand"):
        pm_str = pm["brand"]
    else:
        pm_str = "unknown"

    addr = ctx.get("address") or {}
    addr_str = f"{addr.get('street', '')}, {addr.get('city', '')} ({addr.get('delivery_instructions', '')})"

    dashpass = "DashPass member" if ctx.get("is_dashpass_member") else "not a DashPass member"
    credits  = ctx.get("credits_balance", 0)

    return (
        f"\n\nCURRENT CALLER:\n"
        f"  Name: {ctx['full_name']} | Phone: {ctx['phone']} | Email: {ctx['email']}\n"
        f"  {dashpass} | Credits: ${credits:.2f} | Total orders: {ctx['total_orders']}\n"
        f"  Default address: {addr_str}\n"
        f"  Payment: {pm_str}\n"
        f"  Recent orders:\n{orders_text}"
    )


# ── Entrypoint ─────────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext):
    try:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

        customer_phone = ctx.job.metadata or ""
        print(f"[LUPI] Phone from room metadata: {customer_phone!r}")

        observer = SessionObserver()

        async def publish_fsm_stage(stage: str):
            payload = json.dumps({"type": "fsm_stage", "stage": stage})
            try:
                await ctx.room.local_participant.publish_data(
                    payload.encode("utf-8"), reliable=True
                )
                print(f"[FSM] Published stage: {stage}")
            except Exception as e:
                print(f"[FSM] Stage publish failed: {e}")

        fsm = LupiFSM()
        fsm.on_stage_change = lambda stage: asyncio.create_task(publish_fsm_stage(stage))
        print(f"[FSM] Initialized: {fsm.stage.value}")

        state = {"greeting_done": False, "phone_done": False}
        digit_buffer: list[str] = []

        import re as _re

        def _extract_digits(text: str) -> list[str]:
            word_map = {
                'zero':'0','one':'1','two':'2','three':'3','four':'4',
                'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
            }
            results = []
            tokens = text.lower().split()
            for token in tokens:
                clean = ''.join(c for c in token if c.isalnum())
                if clean in word_map:
                    results.append(word_map[clean])
                elif clean.isdigit():
                    results.extend(list(clean))
            return results

        phrase_cache: dict[str, bytes] = {}

        async def precache_phrase(text: str, key: str):
            if os.getenv("USE_RESEMBLE", "false").lower() == "true":
                return
            kokoro_url = os.getenv("KOKORO_URL", "http://127.0.0.1:8880")
            try:
                async with aiohttp.ClientSession() as http:
                    async with http.post(
                        f"{kokoro_url}/synthesize_cache",
                        json={"text": text, "voice": "af_sarah", "speed": 1.1},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        resp.raise_for_status()
                        pcm_bytes = await resp.read()
                        phrase_cache[key] = pcm_bytes
                        print(f"[CACHE] Pre-synthesized '{key}': {len(pcm_bytes)} bytes")
            except Exception as e:
                print(f"[CACHE] Failed to cache '{key}': {e}")

        # ── Plugins ────────────────────────────────────────────────────────────────
        kokoro_url = os.getenv("KOKORO_URL", "http://127.0.0.1:8880")

        lupi_stt = deepgram.STT(
            model="nova-2",
            language="en-US",
            punctuate=True,
            smart_format=True,
        )
        use_resemble = os.getenv("USE_RESEMBLE", "false").lower() == "true"
        if use_resemble:
            lupi_tts = ResembleTTS(
                api_key=os.getenv("RESEMBLE_API_KEY"),
                voice_uuid=os.getenv("RESEMBLE_VOICE_UUID"),
                rate="100%"
            )
            print("[TTS] Using Resemble AI")
        else:
            lupi_tts = KokoroTTSPlugin(voice="af_sarah", speed=1.1, base_url=kokoro_url)
            print("[TTS] Using Kokoro local")

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

        # Pre-cache disclaimer only — FSM phrases are dynamic and spoken directly
        async def _run_cache():
            await precache_phrase(
                "Just so you know, this call may be recorded for quality and security purposes.",
                "disclaimer"
            )
        cache_task = asyncio.create_task(_run_cache())

        # ── Tools ──────────────────────────────────────────────────────────────────

        # Plain Python dict — used by FSM on_enter to call tools directly without LLM
        tools_registry = {
            "get_order_details": get_order_details,
            "get_order_status": get_order_status,
    "issue_refund": issue_refund,
            "create_support_ticket": create_support_ticket,
        }

        # Only get_dasher_location remains as an LLM-callable tool
        @lk_llm.function_tool(
            name="get_dasher_location",
            description=(
                "Get the most recent GPS event for the dasher on an active order. "
                "Use when the customer asks where their dasher is or how far away they are."
            ),
        )
        async def tool_get_dasher_location(order_number: str) -> str:
            result = await get_dasher_location(order_number)
            return str(result)

        all_tools_dict = {
            "get_dasher_location": tool_get_dasher_location,
        }

        # ── Agent ──────────────────────────────────────────────────────────────────

        agent = Agent(
            instructions=fsm.get_prompt(),
            tools=fsm.get_tools(all_tools_dict),
        )

        def rebuild_agent():
            agent._instructions = fsm.get_prompt()
            agent._tools = fsm.get_tools(all_tools_dict)
            print(f"[FSM] Rebuilt for stage: {fsm.stage.value} | tools: {STAGE_TOOLS[fsm.stage]}")

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

        # ── Async task helpers ─────────────────────────────────────────────────────

        async def _do_phone_lookup(phone: str):
            result = await get_customer_context(phone)
            if result.get("error"):
                state["phone_done"] = False
                digit_buffer.clear()
                try:
                    session.say(
                        "I wasn't able to find an account with that number. Can you try again?",
                        allow_interruptions=True,
                    )
                except RuntimeError:
                    pass
                return
            fsm.customer_ctx = result
            fsm.first_name = (result.get("full_name") or "").split()[0]
            orders = result.get("recent_orders") or []
            if orders:
                fsm.order_number = orders[0].get("order_number", "")
            await fsm.enter("phone_collected", session, tools_registry)
            rebuild_agent()

        async def _classify_and_enter(transcript: str):
            issue_type = await classify_issue(transcript)
            fsm.issue_type = issue_type
            await fsm.enter("issue_detected", session, tools_registry)
            rebuild_agent()
            await fsm.enter("eligibility_checked", session, tools_registry)
            rebuild_agent()

        async def _enter_greeted():
            await asyncio.sleep(0.5)
            try:
                await fsm.enter("greeted", session, tools_registry)
                rebuild_agent()
                print("[FSM] greeted transition complete")
            except Exception as e:
                print(f"[FSM] _enter_greeted error: {e}")

        async def _handle_follow_up():
            await fsm.enter("follow_up_question", session, tools_registry)
            rebuild_agent()

        async def _ask_for_more_digits():
            await asyncio.sleep(0.1)
            try:
                session.say("Can I get the rest of your number?", allow_interruptions=True)
            except RuntimeError:
                pass

        # ── Observability hooks ────────────────────────────────────────────────────

        @session.on("user_input_transcribed")
        def on_user_speech(ev):
            if not ev.is_final:
                return
            observer.on_user_speech(ev.transcript)

            if not state["greeting_done"]:
                print(f"[LUPI] Ignoring early transcript, greeting not done yet: {ev.transcript}")
                return

            # INTRO: interrupt any preemptive generation, then advance FSM
            if fsm.stage == LupiStage.INTRO:
                asyncio.create_task(_enter_greeted())
                return

            if fsm.stage == LupiStage.PHONE_COLLECTION:
                try:
                    session.interrupt()
                except Exception:
                    pass
                new_digits = _extract_digits(ev.transcript)
                if new_digits:
                    digit_buffer.extend(new_digits)
                    print(f"[PHONE] Buffer: {''.join(digit_buffer)} ({len(digit_buffer)} digits)")
                    if len(digit_buffer) >= 10:
                        state["phone_done"] = True
                        phone = '+1' + ''.join(digit_buffer[:10])
                        print(f"[PHONE] Complete: {phone}")
                        asyncio.create_task(_do_phone_lookup(phone))
                    else:
                        asyncio.create_task(_ask_for_more_digits())
                return

            # ISSUE_COLLECTION: classify → investigation → resolution → closing
            if fsm.stage == LupiStage.ISSUE_COLLECTION:
                asyncio.create_task(_classify_and_enter(ev.transcript))
                return

            # All other stages: pass through to LLM

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

        @session.on("conversation_item_added")
        def on_item_added(ev):
            msg = ev.item
            if hasattr(msg, "role") and msg.role == "assistant":
                response = msg.text_content or ""
                print(f"[AGENT]: {response}")
                observer.on_agent_speech_committed(response)
                if observer.current:
                    asyncio.create_task(publish_turn_metrics(observer.current))
                # Detect FOLLOW_UP signal from LLM
                if "FOLLOW_UP" in response.upper() and fsm.stage == LupiStage.CLOSING:
                    print("[FSM] Follow-up detected — routing back to investigation")
                    asyncio.create_task(_handle_follow_up())

        @session.on("agent_state_changed")
        def on_agent_state(ev):
            if ev.old_state == "speaking" and ev.new_state != "speaking":
                print("[BARGE-IN] Agent interrupted mid-speech")

        @session.on("metrics_collected")
        def on_metrics(ev):
            observer.on_metrics(ev.metrics)

        # ── Start ──────────────────────────────────────────────────────────────────

        participant = await ctx.wait_for_participant()
        print(f"[LUPI] Participant: {participant.identity}")

        await session.start(agent, room=ctx.room)
        asyncio.create_task(publish_fsm_stage(fsm.stage.value))

        @session.on("participant_disconnected")
        def on_disconnect(p):
            print(f"[LUPI] Participant disconnected")

        await asyncio.sleep(2.5)
        try:
            await asyncio.wait_for(cache_task, timeout=8.0)
        except Exception as e:
            print(f"[CACHE] Cache task did not complete: {e}")

        try:
            if "disclaimer" in phrase_cache:
                print("[LUPI] Playing cached disclaimer")
            session.say(
                "Just so you know, this call may be recorded for quality and security purposes.",
                allow_interruptions=False,
            )
            await asyncio.sleep(2.5)

            greeting = "Hi, this is Lupi from LupiDash. How are you today?"
            print(f"[LUPI] Greeting: {greeting}")
            session.say(greeting, allow_interruptions=True)
            await asyncio.sleep(0.1)
            state["greeting_done"] = True
            print("[LUPI] Greeting complete, ready for input")
        except RuntimeError as e:
            print(f"[LUPI] Session already closing, skipping greeting: {e}")

        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            print("[LUPI] Session ended cleanly")
            observer.print_summary()
    except Exception as e:
        import traceback
        print(f"[LUPI-AGENT] FATAL ERROR in entrypoint: {e}")
        traceback.print_exc()
        raise


# ── Worker ─────────────────────────────────────────────────────────────────────

print(f"[LUPI-AGENT] Starting up, Python {sys.version}")
print(f"[LUPI-AGENT] Importing dependencies...")

try:
    from lupi.fsm import LupiFSM, LupiStage
    print("[LUPI-AGENT] FSM import OK")
except Exception as e:
    print(f"[LUPI-AGENT] FSM import FAILED: {e}")

try:
    from lupi.classifier import classify_issue
    print("[LUPI-AGENT] Classifier import OK")
except Exception as e:
    print(f"[LUPI-AGENT] Classifier import FAILED: {e}")

try:
    from lupi.tools import get_order_details
    print("[LUPI-AGENT] Tools import OK")
except Exception as e:
    print(f"[LUPI-AGENT] Tools import FAILED: {e}")

if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="lupi-agent",
    ))
