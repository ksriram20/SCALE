FROM python:3.12-slim

WORKDIR /app

# poppler-utils -> pdftotext (PDF extraction); ffmpeg -> audio mastering.
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install the package (with the UI extra) so `scale` and `scale ui` both work.
COPY pyproject.toml requirements.txt ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[ui,rag]"

# config/ and skills/ are also mounted as volumes in docker-compose, so host
# edits apply live; these COPYs make the image self-contained without mounts too.
COPY config/ ./config/
COPY skills/ ./skills/

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["scale"]
CMD ["run", "--episode", "1"]
