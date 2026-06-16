from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)


class CachedHttpClient:
    def __init__(
        self,
        cache_dir: Path,
        timeout_seconds: int = 20,
        max_retries: int = 3,
        backoff_seconds: float = 0.75,
        cache_ttl_seconds: int = 900,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_text(self, url: str) -> str:
        cache_path = self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.txt"
        cache_is_fresh = (
            cache_path.exists()
            and time.time() - cache_path.stat().st_mtime < self.cache_ttl_seconds
        )
        if cache_is_fresh:
            return cache_path.read_text(encoding="utf-8")

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "market-intelligence-agent/0.1"},
                )
                response.raise_for_status()
                cache_path.write_text(response.text, encoding="utf-8")
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                sleep_for = self.backoff_seconds * (2**attempt)
                LOGGER.warning(
                    "http_request_failed url=%s attempt=%s retry_in=%.2f",
                    url,
                    attempt + 1,
                    sleep_for,
                )
                time.sleep(sleep_for)
        raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error
