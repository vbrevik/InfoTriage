# ingest-youtube adapter (Phase 4, D-10/D-11)
# Build context: project root
FROM python:3.12-slim

WORKDIR /app

# 0. Install ffmpeg for audio extraction used by yt-dlp + faster-whisper.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*

# 1. Copy and install local libs without their external deps
COPY libs/contracts /build/contracts
COPY libs/store /build/store
COPY libs/ingest_common /build/ingest_common
RUN pip install --no-deps /build/contracts /build/store /build/ingest_common

# 2. Install adapter dependencies + JSON formatter for structured logging (Phase 7)
COPY apps/ingest-youtube/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt json-log-formatter

# 2.5 Optionally pre-download the faster-whisper model so the first real
# transcription does not have to fetch weights at runtime. Set
# --build-arg PRELOAD_WHISPER_MODEL=tiny to enable.
ARG PRELOAD_WHISPER_MODEL=
ENV INFOTRIAGE_WHISPER_MODEL=${PRELOAD_WHISPER_MODEL:-tiny}
RUN if [ -n "$PRELOAD_WHISPER_MODEL" ]; then python - <<'PY'
import os
from faster_whisper import WhisperModel
model_name = os.environ["INFOTRIAGE_WHISPER_MODEL"]
WhisperModel(model_name, device="cpu", compute_type="int8")
PY
fi

# 3. Copy adapter source
COPY apps/ingest-youtube/ .

# data/feeds is bind-mounted by docker-compose; data/blobs for blob storage
COPY libs/contracts/src/contracts/uvicorn-log-config.json /app/uvicorn-log-config.json

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/uvicorn-log-config.json"]
