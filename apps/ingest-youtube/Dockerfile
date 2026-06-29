FROM python:3.12-slim

WORKDIR /app

# Copy and install local libs without their external deps (wheels installed next)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
COPY libs/ingest_common /build/ingest_common
RUN pip install --no-deps /build/contracts /build/store /build/ingest_common

# Install adapter dependencies (yt-dlp from official yt-dlp/yt-dlp; T-04-SC)
COPY apps/ingest-youtube/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy adapter source
COPY apps/ingest-youtube/ .

# data/feeds is bind-mounted by docker-compose (Plan 06) for Atom XML output
# data/blobs is bind-mounted for content-addressed blob storage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
