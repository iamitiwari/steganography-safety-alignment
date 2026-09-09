"""Thin OpenAI-compatible chat client with on-disk caching and retries.

Works unchanged against llama-server (local CPU), vLLM (cloud GPU), or any
hosted OpenAI-compatible endpoint. Every call is cached by a hash of
(model, messages, sampling params, sample_idx) so reruns are free and
interrupted sweeps resume.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI


@dataclass
class Endpoint:
    base_url: str = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8091/v1")
    api_key: str = os.environ.get("LLM_API_KEY", "none")
    model: str = os.environ.get("LLM_MODEL", "local")
    # Human-readable label written into result records.
    label: str = os.environ.get("LLM_LABEL", "qwen2.5-7b-instruct-q8")
    timeout: float = 1800.0
    max_retries: int = 4


@dataclass
class Completion:
    text: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cached: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    def __init__(self, endpoint: Endpoint, cache_dir: str | Path = "results/cache"):
        self.ep = endpoint
        self.client = OpenAI(base_url=endpoint.base_url, api_key=endpoint.api_key,
                             timeout=endpoint.timeout, max_retries=0)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ cache
    def _key(self, messages, temperature, max_tokens, sample_idx, extra) -> str:
        payload = json.dumps({
            "model": self.ep.model, "label": self.ep.label, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
            "sample_idx": sample_idx, "extra": extra,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    # ------------------------------------------------------------------- call
    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.6,
             max_tokens: int = 1500, sample_idx: int = 0, seed: int | None = None,
             extra: dict | None = None, use_cache: bool = True) -> Completion:
        extra = extra or {}
        key = self._key(messages, temperature, max_tokens, sample_idx, extra)
        path = self._cache_path(key)
        if use_cache and path.exists():
            try:
                d = json.loads(path.read_text())
                return Completion(**{**d, "cached": True})
            except (json.JSONDecodeError, TypeError, OSError):
                # Partially-written or stale cache entry: treat as a miss.
                pass

        if seed is None:
            # Distinct seed per sample so llama-server's sampler diverges across samples
            # at the same temperature; harmless on backends that ignore seed.
            seed = int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % (2**31)

        last_err: Exception | None = None
        for attempt in range(self.ep.max_retries + 1):
            try:
                t0 = time.time()
                resp = self.client.chat.completions.create(
                    model=self.ep.model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, seed=seed, **extra)
                dt = time.time() - t0
                choice = resp.choices[0]
                comp = Completion(
                    text=choice.message.content or "",
                    finish_reason=choice.finish_reason or "",
                    prompt_tokens=resp.usage.prompt_tokens if resp.usage else -1,
                    completion_tokens=resp.usage.completion_tokens if resp.usage else -1,
                    latency_s=dt,
                    raw={"id": resp.id, "model": resp.model, "seed": seed},
                )
                # Some backends expose <think>...</think> reasoning in a separate field.
                reasoning = getattr(choice.message, "reasoning_content", None) or \
                    getattr(choice.message, "reasoning", None)
                if reasoning and "<think>" not in comp.text:
                    comp.text = f"<think>\n{reasoning}\n</think>\n{comp.text}"
                blob = json.dumps({
                    "text": comp.text, "finish_reason": comp.finish_reason,
                    "prompt_tokens": comp.prompt_tokens,
                    "completion_tokens": comp.completion_tokens,
                    "latency_s": comp.latency_s, "raw": comp.raw})
                with self._lock:
                    # Atomic: concurrent threads may share a cache key when two
                    # rollouts produce byte-identical prompts.
                    tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
                    tmp.write_text(blob)
                    tmp.replace(path)
                return comp
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"LLM call failed after retries: {last_err}")
