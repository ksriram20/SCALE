"""OpenRouter chat client with free-model rotation and rate-limit handling.

Strategy: try each model in `llm.models` in order. On a 429 (rate-limited) or an
empty response, rotate to the next model. When every model in the list is
exhausted, sleep `cooldown_seconds` and start the rotation over, up to
`max_retries` full passes. This lets a stack of free models run unattended:
it slows down rather than failing when limits are hit.
"""

import logging
import time

import requests

from .config import env

log = logging.getLogger("cale.llm")


class RateLimited(Exception):
    """Raised internally to signal 'move to the next model'."""


def is_free_model(model, provider):
    """Whether a model id is guaranteed free of charge.

    OpenRouter free variants always end in ':free'. For other providers (e.g.
    Ollama cloud) the free tier isn't encoded in the id, so we trust the curated
    `llm.models` list instead of a name check.
    """
    if provider == "openrouter":
        return model.strip().lower().endswith(":free")
    return True


class OpenRouterClient:
    def __init__(self, cfg):
        c = cfg["llm"]
        self.provider = c.get("provider", "openrouter")
        self.base_url = c["base_url"].rstrip("/")
        self.models = c["models"]
        self.free_only = c.get("free_only", True)
        self.json_mode = c.get("json_mode", True)   # some providers reject response_format
        self.temperature = c.get("temperature", 0.4)
        self.max_tokens = c.get("max_tokens", 4000)
        self.cooldown = c.get("cooldown_seconds", 900)
        self.max_retries = c.get("max_retries", 5)
        self.timeout = c.get("request_timeout", 120)

        api_key_env = c.get("api_key_env", "OPENROUTER_API_KEY")
        self.api_key = env(api_key_env)
        if not self.api_key:
            raise RuntimeError(f"{api_key_env} not set — copy .env.example to .env")
        self.app_name = env("OPENROUTER_APP_NAME", "SCALE")

        # Hard guard: refuse to even start if free_only is on and any configured
        # model is not free. Fails loud at startup, before any request is sent.
        if self.free_only:
            paid = [m for m in self.models if not is_free_model(m, self.provider)]
            if paid:
                raise RuntimeError(
                    "llm.free_only is on but these configured models are NOT free: "
                    f"{paid}. For OpenRouter, free models must end in ':free'. "
                    "Fix the list or set llm.free_only: false to allow paid models."
                )
        log.info("provider=%s free_only=%s models=%s", self.provider, self.free_only, self.models)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_name,
            "HTTP-Referer": "https://github.com/local/cale",
        }

    def chat(self, system, user, temperature=None, json_mode=False):
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode and self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        for attempt in range(self.max_retries):
            for model in self.models:
                payload["model"] = model
                try:
                    return self._call(payload, model)
                except RateLimited:
                    log.warning("rate-limited/empty on %s — next model", model)
                    continue
            log.warning(
                "all free models exhausted (pass %d/%d) — sleeping %ds",
                attempt + 1, self.max_retries, self.cooldown,
            )
            time.sleep(self.cooldown)
        raise RuntimeError("exhausted all models and retries — try again later")

    def _call(self, payload, model):
        # Belt-and-suspenders: never send a paid model when free_only is on.
        if self.free_only and not is_free_model(model, self.provider):
            raise RuntimeError(f"refusing to call non-free model: {model}")
        backoff = 5
        for _ in range(4):
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 429:
                raise RateLimited(model)
            if resp.status_code in (400, 402, 403, 404):
                # retired/unavailable/forbidden (e.g. a provider's content filter) —
                # rotate to the next model, which may be less restrictive.
                log.warning("model unavailable (HTTP %s) on %s — skipping: %s",
                            resp.status_code, model, resp.text[:140])
                raise RateLimited(model)
            if resp.status_code >= 500:
                log.warning("HTTP %s on %s — backoff %ds", resp.status_code, model, backoff)
                time.sleep(backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            content = choices[0]["message"]["content"] if choices else ""
            if not content or not content.strip():
                raise RateLimited(model)
            usage = data.get("usage", {})
            log.info("ok %s (%s tok)", model, usage.get("total_tokens", "?"))
            return content.strip()
        raise RateLimited(model)
