FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

WORKDIR /app

RUN pip install --no-cache-dir \
    chatterbox-tts \
    torchaudio \
    fastapi \
    uvicorn \
    numpy

COPY chatterbox_server.py .

EXPOSE 8881

CMD ["uvicorn", "chatterbox_server:app", "--host", "0.0.0.0", "--port", "8881"]
