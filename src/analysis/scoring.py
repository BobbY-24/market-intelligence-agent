from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreInputs:
    direct_relevance: float
    materiality: float
    source_reliability: float
    recency: float
    novelty: float
    market_reaction: float
    long_term_impact: float
    multi_asset_impact: float
    association_confidence: float


def importance_score(inputs: ScoreInputs) -> int:
    weights = {
        "direct_relevance": 0.18,
        "materiality": 0.18,
        "source_reliability": 0.12,
        "recency": 0.10,
        "novelty": 0.10,
        "market_reaction": 0.10,
        "long_term_impact": 0.10,
        "multi_asset_impact": 0.07,
        "association_confidence": 0.05,
    }
    raw = sum(getattr(inputs, key) * weight for key, weight in weights.items())
    return max(0, min(100, round(raw)))

