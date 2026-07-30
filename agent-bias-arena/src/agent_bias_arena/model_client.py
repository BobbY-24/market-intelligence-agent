"""Transparent Ollama and deterministic mock model clients."""

from __future__ import annotations

import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import ModelConfig

LOGGER = logging.getLogger(__name__)
ChatMessage = dict[str, str]


class ModelClientError(RuntimeError):
    """Raised after a model request exhausts its retry limit."""


class ModelClient(ABC):
    """Small common interface used by agents."""

    @abstractmethod
    def generate(
        self, messages: list[ChatMessage], *, context: dict[str, Any] | None = None
    ) -> str:
        """Generate one response from a fresh list of episode-local messages."""


class OllamaClient(ModelClient):
    """Client for Ollama's local `/api/chat` HTTP endpoint."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def generate(
        self, messages: list[ChatMessage], *, context: dict[str, Any] | None = None
    ) -> str:
        options: dict[str, Any] = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        if self.config.seed is not None:
            options["seed"] = self.config.seed
        if self.config.max_tokens is not None:
            options["num_predict"] = self.config.max_tokens
        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if context and context.get("structured"):
            payload["format"] = "json"

        last_error: Exception | None = None
        endpoint = f"{self.config.base_url.rstrip('/')}/api/chat"
        for attempt in range(self.config.request_retries + 1):
            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    response = client.post(endpoint, json=payload)
                    response.raise_for_status()
                body = response.json()
                content = body.get("message", {}).get("content")
                if not isinstance(content, str):
                    raise ModelClientError("Ollama response did not contain message.content")
                return content
            except (httpx.HTTPError, ValueError, ModelClientError) as exc:
                last_error = exc
                LOGGER.warning(
                    "Ollama request failed (attempt %s/%s): %s",
                    attempt + 1,
                    self.config.request_retries + 1,
                    exc,
                )
                if attempt < self.config.request_retries:
                    time.sleep(min(0.25 * (2**attempt), 2.0))
        raise ModelClientError(f"Ollama request failed after retries: {last_error}")


class MockModelClient(ModelClient):
    """Seeded mock supporting preferences, peer adoption, and malformed responses."""

    def __init__(self, config: ModelConfig, seed: int) -> None:
        self.config = config
        self._rng = random.Random(seed)
        self.requests: list[list[ChatMessage]] = []

    def generate(
        self, messages: list[ChatMessage], *, context: dict[str, Any] | None = None
    ) -> str:
        context = context or {}
        self.requests.append([dict(message) for message in messages])
        if (
            self.config.mock_malformed_first_attempt
            and context.get("structured")
            and context.get("attempt") == 0
        ):
            return "I cannot format this {selected_candidate: A"

        stage = str(context.get("stage", "initial"))
        if stage in {"argument", "response"}:
            choice = self._choice(context, final=False)
            label = "a tie" if choice == "TIE" else f"Candidate {choice}"
            return (
                f"I recommend {label}. The qualifications are balanced, so this judgment "
                "uses only the documented role-relevant evidence."
            )

        choice = self._choice(context, final=stage == "final")
        initial = context.get("initial_choice")
        decision: dict[str, Any] = {
            "selected_candidate": choice,
            "confidence": 0.67,
            "reason_codes": ["skills", "experience"],
            "short_rationale": "The selected profile is at least as aligned on stated criteria.",
        }
        if stage == "final":
            decision["changed_from_initial_decision"] = choice != initial
        return json.dumps(decision, sort_keys=True)

    def _choice(self, context: dict[str, Any], *, final: bool) -> str:
        biased_choice = context.get("biased_preferred_candidate")
        if biased_choice in {"A", "B"}:
            return str(biased_choice)

        behavior = self.config.mock_behavior
        if behavior == "prefer_a":
            return "A"
        if behavior == "prefer_b":
            return "B"
        peer = context.get("peer_recommendation")
        if final and (behavior == "adopt_peer" or self.config.mock_adopt_peer):
            if peer in {"A", "B", "TIE"}:
                return str(peer)
        initial = context.get("initial_choice")
        if final and initial in {"A", "B", "TIE"}:
            return str(initial)
        return self._rng.choice(["A", "B"])


def create_model_client(config: ModelConfig, seed: int) -> ModelClient:
    """Create the configured backend without model-specific agent behavior."""
    if config.backend == "ollama":
        return OllamaClient(config)
    return MockModelClient(config, seed)
