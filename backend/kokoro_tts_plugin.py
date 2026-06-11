import io
import time
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from typing import Optional

from livekit.agents import tts, utils
from livekit import rtc
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

KOKORO_URL = "http://127.0.0.1:8880"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1


class KokoroTTS(tts.TTS):
    def __init__(
        self,
        voice: str = "af_heart",
        speed: float = 1.0,
        base_url: str = KOKORO_URL,
    ):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._voice = voice
        self._speed = speed
        self._base_url = base_url
        self.last_ttfc_ms: int = 0

    @asynccontextmanager
    async def synthesize(self, text: str, *, conn_options: Optional[APIConnectOptions] = None, **kwargs):
        conn_options = conn_options or DEFAULT_API_CONNECT_OPTIONS
        stream = KokoroChunkedStream(
            tts=self,
            text=text,
            voice=self._voice,
            speed=self._speed,
            base_url=self._base_url,
            conn_options=conn_options,
        )
        try:
            yield stream
        finally:
            await stream.aclose()

    def stream(self, *, conn_options: Optional[APIConnectOptions] = None, **kwargs):
        conn_options = conn_options or DEFAULT_API_CONNECT_OPTIONS
        return KokoroChunkedStream(
            tts=self,
            text="",
            voice=self._voice,
            speed=self._speed,
            base_url=self._base_url,
            conn_options=conn_options,
        )


class KokoroChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts, text: str, voice: str, speed: float, base_url: str, conn_options=None):
        super().__init__(tts=tts, input_text=text, conn_options=conn_options or DEFAULT_API_CONNECT_OPTIONS)
        self._text = text
        self._voice = voice
        self._speed = speed
        self._base_url = base_url

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        text = self._text.strip()
        if not text:
            return

        t_start = time.perf_counter()
        request_id = utils.shortuuid()
        output_emitter.initialize(
            request_id=request_id,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/pcm",
            stream=False,
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/synthesize_stream",
                    json={
                        "text": text,
                        "voice": self._voice,
                        "speed": self._speed,
                    },
                    timeout=aiohttp.ClientTimeout(total=30, connect=5),
                ) as resp:
                    resp.raise_for_status()
                    first = True
                    total_bytes = 0
                    async for chunk in resp.content.iter_chunked(4096):
                        if chunk:
                            if first:
                                ttfc = int((time.perf_counter() - t_start) * 1000)
                                print(f"[KOKORO] First audio chunk in {ttfc}ms")
                                self._tts.last_ttfc_ms = ttfc
                                first = False
                            output_emitter.push(chunk)
                            total_bytes += len(chunk)

            elapsed = int((time.perf_counter() - t_start) * 1000)
            print(f"[KOKORO] {len(text)} chars | {total_bytes} bytes | {elapsed}ms total")

        except Exception as e:
            print(f"[KOKORO] Error: {e}")
            raise
