"""
Kokoro TTS local streaming server - Linux compatible (CPU/CUDA)
Uses the standard `kokoro` package (not kokoro-mlx).
Same API contract as kokoro_server.py for drop-in replacement.
"""
import io
import os
import re
import time
import struct
import asyncio
import numpy as np
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI()

# ── Model loading ──────────────────────────────────────────────────────────────

print("[KOKORO] Loading model...")
t_start = time.perf_counter()

from kokoro import KPipeline

# Use American English by default; set KOKORO_LANG env to override
lang = os.getenv("KOKORO_LANG", "a")
pipeline = KPipeline(lang_code=lang)

load_time = int((time.perf_counter() - t_start) * 1000)
print(f"[KOKORO] Model ready in {load_time}ms")

# Discover available voices
_voices_dir = None
try:
    import kokoro
    import pathlib
    _pkg_dir = pathlib.Path(kokoro.__file__).parent
    _voices_dir = _pkg_dir / "assets" / "voices"
    if _voices_dir.exists():
        available_voices = sorted([p.stem for p in _voices_dir.glob("*.pt")])
    else:
        available_voices = []
except Exception:
    available_voices = []
print(f"[KOKORO] Available voices: {available_voices[:10]}")

SAMPLE_RATE = 24000

# ── Request schema ─────────────────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0
    sample_rate: int = 24000


# ── Helpers ────────────────────────────────────────────────────────────────────

def numpy_to_pcm16(audio: np.ndarray) -> bytes:
    """Convert float32 numpy array to 16-bit PCM bytes"""
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767).astype(np.int16).tobytes()


def make_wav_header(sample_rate: int, num_samples: int) -> bytes:
    """Generate a WAV header for the given parameters"""
    num_channels = 1
    bits_per_sample = 16
    data_size = num_samples * num_channels * bits_per_sample // 8
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    return struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, num_channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b'data', data_size
    )


def _generate_full(text: str, voice: str, speed: float) -> np.ndarray:
    """Run the pipeline and concatenate all audio segments."""
    segments = []
    for _, _, audio in pipeline(text, voice=voice, speed=speed):
        if audio is not None:
            segments.append(audio.numpy() if hasattr(audio, "numpy") else np.array(audio))
    if not segments:
        return np.array([], dtype=np.float32)
    return np.concatenate(segments)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/synthesize")
async def synthesize(request: TTSRequest):
    """Non-streaming synthesis - returns full WAV file"""
    t_start = time.perf_counter()
    loop = asyncio.get_event_loop()

    audio = await loop.run_in_executor(
        None, _generate_full, request.text, request.voice, request.speed
    )

    elapsed = int((time.perf_counter() - t_start) * 1000)
    print(f"[KOKORO] Synthesized {len(request.text)} chars in {elapsed}ms")

    pcm_bytes = numpy_to_pcm16(audio)
    wav_bytes = make_wav_header(SAMPLE_RATE, len(audio)) + pcm_bytes

    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={
            "X-Synthesis-Ms": str(elapsed),
            "X-Sample-Rate": str(SAMPLE_RATE),
        }
    )


@app.post("/synthesize_stream")
async def synthesize_stream(request: TTSRequest):
    """Streaming synthesis - yields PCM chunks per sentence for low TTFA"""
    t_start = time.perf_counter()

    async def generate_chunks():
        loop = asyncio.get_event_loop()

        # Split into sentences for progressive delivery
        text = request.text.strip()
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return

        first = True
        for sentence in sentences:
            def synthesize_sentence(s=sentence):
                return _generate_full(s, request.voice, request.speed)

            audio = await loop.run_in_executor(None, synthesize_sentence)
            pcm = numpy_to_pcm16(audio)

            if first:
                ttfc = int((time.perf_counter() - t_start) * 1000)
                print(f"[KOKORO] First sentence in {ttfc}ms: '{sentence[:40]}'")
                first = False

            yield pcm

        total = int((time.perf_counter() - t_start) * 1000)
        print(f"[KOKORO] All sentences done in {total}ms for {len(text)} chars")

    return StreamingResponse(
        generate_chunks(),
        media_type="audio/octet-stream",
        headers={
            "X-Sample-Rate": "24000",
            "X-Channels": "1",
            "X-Bit-Depth": "16",
            "Cache-Control": "no-cache",
        }
    )


@app.get("/health")
async def health():
    return {"status": "ok", "model": "kokoro", "load_ms": load_time}


@app.post("/synthesize_cache")
async def synthesize_cache(request: TTSRequest):
    """Pre-synthesize a phrase and return raw PCM bytes for caching."""
    loop = asyncio.get_event_loop()

    audio = await loop.run_in_executor(
        None, _generate_full, request.text, request.voice, request.speed
    )
    pcm = numpy_to_pcm16(audio)

    print(f"[KOKORO CACHE] Pre-synthesized {len(request.text)} chars -> {len(pcm)} bytes")
    return StreamingResponse(
        io.BytesIO(pcm),
        media_type="audio/octet-stream",
        headers={"X-Sample-Rate": "24000", "X-Channels": "1", "X-Bit-Depth": "16"},
    )


@app.get("/voices")
async def voices():
    return {"voices": available_voices, "count": len(available_voices)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8880"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
