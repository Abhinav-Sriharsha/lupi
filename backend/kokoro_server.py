"""
Kokoro TTS local streaming server - Python 3.12 + MLX on Apple Silicon
Streams audio chunks as they are synthesized for minimum latency
"""
import io
import time
import struct
import asyncio
import numpy as np
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI()

print("[KOKORO] Loading model...")
t_start = time.perf_counter()
from kokoro_mlx import KokoroTTS
tts_model = KokoroTTS.from_pretrained("mlx-community/Kokoro-82M-bf16")
load_time = int((time.perf_counter() - t_start) * 1000)
print(f"[KOKORO] Model ready in {load_time}ms")
print(f"[KOKORO] Available voices: {tts_model.list_voices()[:10]}")

class TTSRequest(BaseModel):
    text: str
    voice: str = "am_michael"
    speed: float = 1.0
    sample_rate: int = 24000

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

@app.post("/synthesize")
async def synthesize(request: TTSRequest):
    """Non-streaming synthesis - returns full WAV file"""
    t_start = time.perf_counter()

    result = tts_model.generate(
        request.text,
        voice=request.voice,
        speed=request.speed,
    )

    audio = np.array(result.audio)
    elapsed = int((time.perf_counter() - t_start) * 1000)
    print(f"[KOKORO] Synthesized {len(request.text)} chars in {elapsed}ms")

    pcm_bytes = numpy_to_pcm16(audio)
    wav_bytes = make_wav_header(result.sample_rate, len(audio)) + pcm_bytes

    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={
            "X-Synthesis-Ms": str(elapsed),
            "X-Sample-Rate": str(result.sample_rate),
        }
    )

@app.post("/synthesize_stream")
async def synthesize_stream(request: TTSRequest):
    t_start = time.perf_counter()

    async def generate_chunks():
        loop = asyncio.get_event_loop()

        # Split into sentences for progressive delivery
        import re
        text = request.text.strip()
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return

        first = True
        for sentence in sentences:
            def synthesize_sentence(s=sentence):
                result = tts_model.generate(
                    s,
                    voice=request.voice,
                    speed=request.speed,
                )
                audio = np.array(result.audio)
                return numpy_to_pcm16(audio)

            pcm = await loop.run_in_executor(None, synthesize_sentence)

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
    return {"status": "ok", "model": "Kokoro-82M-bf16", "load_ms": load_time}

@app.post("/synthesize_cache")
async def synthesize_cache(request: TTSRequest):
    """Pre-synthesize a phrase and return raw PCM bytes for caching."""
    loop = asyncio.get_event_loop()

    def generate():
        result = tts_model.generate(
            request.text,
            voice=request.voice,
            speed=request.speed,
        )
        audio = np.array(result.audio)
        return numpy_to_pcm16(audio)

    pcm = await loop.run_in_executor(None, generate)
    elapsed = int(time.perf_counter() * 1000)
    print(f"[KOKORO CACHE] Pre-synthesized {len(request.text)} chars → {len(pcm)} bytes")
    return StreamingResponse(
        io.BytesIO(pcm),
        media_type="audio/octet-stream",
        headers={"X-Sample-Rate": "24000", "X-Channels": "1", "X-Bit-Depth": "16"},
    )

@app.get("/voices")
async def voices():
    all_voices = tts_model.list_voices()
    return {"voices": all_voices, "count": len(all_voices)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8880, log_level="warning")
