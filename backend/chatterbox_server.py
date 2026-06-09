"""
Chatterbox Turbo TTS local streaming server
Drop-in replacement for kokoro_server.py — same API contract, port 8881.
Streams audio chunks at sentence boundaries for minimum first-chunk latency.
"""
import io
import re
import time
import struct
import asyncio
import numpy as np
import torch
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# Device selection: CUDA > MPS > CPU
if torch.cuda.is_available():
    DEVICE = "cuda"
elif torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"

print(f"[CHATTERBOX] Loading model on {DEVICE}...")
t_start = time.perf_counter()
from chatterbox.tts_turbo import ChatterboxTurboTTS
tts_model = ChatterboxTurboTTS.from_pretrained(device=DEVICE)
load_time = int((time.perf_counter() - t_start) * 1000)
print(f"[CHATTERBOX] Model ready in {load_time}ms")

SAMPLE_RATE = 24000


class TTSRequest(BaseModel):
    text: str
    voice: str = "default"
    speed: float = 1.0
    sample_rate: int = SAMPLE_RATE
    audio_prompt_path: Optional[str] = None


def numpy_to_pcm16(audio: np.ndarray) -> bytes:
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767).astype(np.int16).tobytes()


def make_wav_header(sample_rate: int, num_samples: int) -> bytes:
    num_channels = 1
    bits_per_sample = 16
    data_size = num_samples * num_channels * bits_per_sample // 8
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )


def _synthesize_text(text: str, audio_prompt_path: Optional[str]) -> np.ndarray:
    """Run synthesis synchronously; returns float32 numpy array."""
    kwargs = {}
    if audio_prompt_path:
        kwargs["audio_prompt_path"] = audio_prompt_path

    wav = tts_model.generate(text, **kwargs)

    # ChatterboxTurboTTS.generate may return a tensor or ndarray
    if isinstance(wav, torch.Tensor):
        wav = wav.squeeze().cpu().numpy()
    else:
        wav = np.array(wav).squeeze()

    return wav.astype(np.float32)


@app.get("/health")
async def health():
    return {"status": "ok", "model": "chatterbox-turbo", "load_ms": load_time}


@app.post("/synthesize")
async def synthesize(request: TTSRequest):
    """Non-streaming synthesis — returns full WAV file."""
    t0 = time.perf_counter()
    loop = asyncio.get_event_loop()

    audio = await loop.run_in_executor(
        None, _synthesize_text, request.text, request.audio_prompt_path
    )

    elapsed = int((time.perf_counter() - t0) * 1000)
    print(f"[CHATTERBOX] Synthesized {len(request.text)} chars in {elapsed}ms")

    pcm_bytes = numpy_to_pcm16(audio)
    wav_bytes = make_wav_header(SAMPLE_RATE, len(audio)) + pcm_bytes

    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={
            "X-Synthesis-Ms": str(elapsed),
            "X-Sample-Rate": str(SAMPLE_RATE),
        },
    )


@app.post("/synthesize_stream")
async def synthesize_stream(request: TTSRequest):
    """Streaming synthesis — yields raw int16 PCM at 24000Hz mono, one chunk per sentence."""
    t0 = time.perf_counter()

    async def generate_chunks():
        loop = asyncio.get_event_loop()

        text = request.text.strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return

        first = True
        for sentence in sentences:
            def synthesize_sentence(s=sentence):
                audio = _synthesize_text(s, request.audio_prompt_path)
                return numpy_to_pcm16(audio)

            pcm = await loop.run_in_executor(None, synthesize_sentence)

            if first:
                ttfc = int((time.perf_counter() - t0) * 1000)
                print(f"[CHATTERBOX] First chunk in {ttfc}ms: '{sentence[:40]}'")
                first = False

            yield pcm

        total = int((time.perf_counter() - t0) * 1000)
        print(f"[CHATTERBOX] All sentences done in {total}ms for {len(text)} chars")

    return StreamingResponse(
        generate_chunks(),
        media_type="audio/octet-stream",
        headers={
            "X-Sample-Rate": str(SAMPLE_RATE),
            "X-Channels": "1",
            "X-Bit-Depth": "16",
            "Cache-Control": "no-cache",
        },
    )


@app.post("/synthesize_cache")
async def synthesize_cache(request: TTSRequest):
    """Pre-synthesize a phrase and return raw PCM bytes for caching."""
    loop = asyncio.get_event_loop()

    def generate():
        audio = _synthesize_text(request.text, request.audio_prompt_path)
        return numpy_to_pcm16(audio)

    pcm = await loop.run_in_executor(None, generate)
    print(f"[CHATTERBOX CACHE] Pre-synthesized {len(request.text)} chars → {len(pcm)} bytes")
    return StreamingResponse(
        io.BytesIO(pcm),
        media_type="audio/octet-stream",
        headers={"X-Sample-Rate": str(SAMPLE_RATE), "X-Channels": "1", "X-Bit-Depth": "16"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8881, log_level="warning")
