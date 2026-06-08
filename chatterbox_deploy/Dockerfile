FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

WORKDIR /app

RUN pip install --no-cache-dir \
    "chatterbox-tts" \
    "torchaudio>=2.4.0" \
    fastapi \
    uvicorn \
    numpy \
    "optree>=0.13.0"

COPY chatterbox_server.py .

EXPOSE 8881

CMD ["uvicorn", "chatterbox_server:app", "--host", "0.0.0.0", "--port", "8881"]
