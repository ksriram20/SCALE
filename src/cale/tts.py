"""Kokoro TTS client (local container, OpenAI-compatible /audio/speech)."""

import logging
from pathlib import Path

import requests

from .config import env

log = logging.getLogger("cale.tts")


class KokoroClient:
    def __init__(self, cfg):
        c = cfg["tts"]
        # Env override lets the same config work in Docker (kokoro:8880) and
        # locally (set KOKORO_BASE_URL=http://localhost:8880/v1).
        self.base_url = env("KOKORO_BASE_URL", c["base_url"]).rstrip("/")
        self.voice = c.get("voice", "af_bella")
        self.model = c.get("model", "kokoro")
        self.speed = c.get("speed", 1.0)
        self.format = c.get("format", "mp3")
        self.timeout = 900  # long scripts take a while on CPU

    def synthesize(self, text, out_path):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # The output file extension wins (lets the pipeline request wav for mastering).
        fmt = out_path.suffix.lstrip(".").lower() or self.format
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": fmt,
            "speed": self.speed,
        }
        resp = requests.post(
            f"{self.base_url}/audio/speech",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        log.info("wrote audio %s (%d bytes)", out_path, len(resp.content))
        return out_path
