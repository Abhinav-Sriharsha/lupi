import re
import time
import aiohttp
from contextlib import asynccontextmanager
from typing import Optional

from livekit.agents import tts, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

RESEMBLE_STREAM_URL = "https://f.cluster.resemble.ai/stream"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
WAV_HEADER_BYTES = 44


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sentence_chunks(text: str, max_words: int = 40) -> list[str]:
    sentences = _split_sentences(text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        word_count = len(sentence.split())
        if current and current_words + word_count > max_words:
            chunks.append(" ".join(current))
            current = [sentence]
            current_words = word_count
        else:
            current.append(sentence)
            current_words += word_count
    if current:
        chunks.append(" ".join(current))
    return chunks


class ResembleTTS(tts.TTS):
    def __init__(
        self,
        api_key: str,
        voice_uuid: str,
        rate: str = "100%",
    ):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._api_key = api_key
        self._voice_uuid = voice_uuid
        self._rate = rate

    @asynccontextmanager
    async def synthesize(self, text: str, *, conn_options: Optional[APIConnectOptions] = None, **kwargs):
        conn_options = conn_options or DEFAULT_API_CONNECT_OPTIONS
        stream = ResembleChunkedStream(
            tts=self,
            text=text,
            api_key=self._api_key,
            voice_uuid=self._voice_uuid,
            rate=self._rate,
            conn_options=conn_options,
        )
        try:
            yield stream
        finally:
            await stream.aclose()

    def stream(self, *, conn_options: Optional[APIConnectOptions] = None, **kwargs):
        conn_options = conn_options or DEFAULT_API_CONNECT_OPTIONS
        return ResembleChunkedStream(
            tts=self,
            text="",
            api_key=self._api_key,
            voice_uuid=self._voice_uuid,
            rate=self._rate,
            conn_options=conn_options,
        )


class ResembleChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts, text: str, api_key: str, voice_uuid: str, rate: str, conn_options=None):
        super().__init__(tts=tts, input_text=text, conn_options=conn_options or DEFAULT_API_CONNECT_OPTIONS)
        self._text = text
        self._api_key = api_key
        self._voice_uuid = voice_uuid
        self._rate = rate

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        text = self._text.strip()
        if not text:
            return

        chunks = _sentence_chunks(text)
        t_start = time.perf_counter()
        request_id = utils.shortuuid()
        output_emitter.initialize(
            request_id=request_id,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/pcm",
            stream=False,
        )

        first_audio = True
        total_bytes = 0

        for i, chunk_text in enumerate(chunks):
            ssml = f'<speak><prosody rate="{self._rate}">{chunk_text}</prosody></speak>'
            t_chunk = time.perf_counter()
            chunk_bytes = 0

            try:
                headers = {"Authorization": f"Bearer {self._api_key}"}
                payload = {
                    "voice_uuid": self._voice_uuid,
                    "data": ssml,
                    "precision": "PCM_16",
                    "sample_rate": SAMPLE_RATE,
                    "output_format": "wav",
                }

                connector = aiohttp.TCPConnector(ssl=False, limit=10)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.post(
                        RESEMBLE_STREAM_URL,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60, connect=15),
                    ) as resp:
                        resp.raise_for_status()
                        bytes_to_skip = WAV_HEADER_BYTES
                        async for chunk in resp.content.iter_chunked(4096):
                            if not chunk:
                                continue
                            if bytes_to_skip > 0:
                                skip = min(bytes_to_skip, len(chunk))
                                chunk = chunk[skip:]
                                bytes_to_skip -= skip
                                if not chunk:
                                    continue
                            if first_audio:
                                ttfc = int((time.perf_counter() - t_start) * 1000)
                                print(f"[RESEMBLE] First audio chunk in {ttfc}ms")
                                first_audio = False
                            output_emitter.push(chunk)
                            chunk_bytes += len(chunk)
                            total_bytes += len(chunk)

                chunk_elapsed = int((time.perf_counter() - t_chunk) * 1000)
                print(f"[RESEMBLE] Sentence {i + 1}/{len(chunks)}: '{chunk_text[:50]}' | {chunk_bytes} bytes | {chunk_elapsed}ms")

            except Exception as e:
                print(f"[RESEMBLE] Error on sentence {i + 1}: {e}")
                raise

        elapsed = int((time.perf_counter() - t_start) * 1000)
        print(f"[RESEMBLE] Total: {len(text)} chars | {total_bytes} bytes | {elapsed}ms")
