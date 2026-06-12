FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    espeak-ng \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "kokoro>=0.9.4" \
    "torch" \
    "soundfile" \
    "fastapi" \
    "uvicorn" \
    "numpy"

COPY kokoro_server_linux.py .

EXPOSE 8880

CMD ["sh", "-c", "uvicorn kokoro_server_linux:app --host 0.0.0.0 --port ${PORT:-8880}"]
