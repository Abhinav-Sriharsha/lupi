FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "torch>=2.4.0" \
    "torchaudio>=2.4.0" \
    "transformers>=4.45.0" \
    "accelerate>=0.30.0" \
    "chatterbox-tts" \
    "optree>=0.13.0" \
    fastapi \
    uvicorn \
    numpy

COPY chatterbox_server.py .

EXPOSE 8881

CMD ["uvicorn", "chatterbox_server:app", "--host", "0.0.0.0", "--port", "8881"]
