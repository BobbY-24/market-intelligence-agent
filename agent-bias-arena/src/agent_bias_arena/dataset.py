"""JSONL dataset loading and counterfactual-pair validation."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pydantic import ValidationError

from .schemas import HiringScenario


class DatasetValidationError(ValueError):
    """Raised when one or more dataset invariants fail."""


def load_dataset(path: str | Path) -> list[HiringScenario]:
    """Load and validate a JSONL counterfactual hiring dataset."""
    data_path = Path(path)
    scenarios: list[HiringScenario] = []
    errors: list[str] = []
    for line_number, line in enumerate(data_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            scenarios.append(HiringScenario.model_validate_json(line))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"line {line_number}: {exc}")
    if errors:
        raise DatasetValidationError("Invalid dataset records:\n" + "\n".join(errors))
    validate_counterfactual_pairs(scenarios)
    return scenarios


def validate_counterfactual_pairs(scenarios: list[HiringScenario]) -> None:
    """Validate IDs, exact pair membership, qualification identity, and marker swaps."""
    errors: list[str] = []
    ids = [scenario.scenario_id for scenario in scenarios]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate scenario_id values: {duplicates}")

    by_pair: dict[str, list[HiringScenario]] = defaultdict(list)
    for scenario in scenarios:
        by_pair[scenario.pair_id].append(scenario)

    for pair_id, members in sorted(by_pair.items()):
        variants = {member.variant: member for member in members}
        if len(members) != 2 or set(variants) != {"original", "swapped"}:
            errors.append(f"{pair_id}: expected exactly original and swapped variants")
            continue
        original = variants["original"]
        swapped = variants["swapped"]
        if original.job != swapped.job:
            errors.append(f"{pair_id}: job changed across variants")
        for position in ("candidate_a", "candidate_b"):
            before = getattr(original, position)
            after = getattr(swapped, position)
            if before.qualifications != after.qualifications:
                errors.append(f"{pair_id}: {position} qualifications changed during swap")
            if before.candidate_id != after.candidate_id:
                errors.append(f"{pair_id}: {position} candidate ID changed during swap")
        if original.candidate_a.demographic_group != swapped.candidate_b.demographic_group:
            errors.append(f"{pair_id}: candidate A group marker was not exchanged with B")
        if original.candidate_b.demographic_group != swapped.candidate_a.demographic_group:
            errors.append(f"{pair_id}: candidate B group marker was not exchanged with A")
        if original.candidate_a.pronouns != swapped.candidate_b.pronouns:
            errors.append(f"{pair_id}: candidate A pronouns were not exchanged with B")
        if original.candidate_b.pronouns != swapped.candidate_a.pronouns:
            errors.append(f"{pair_id}: candidate B pronouns were not exchanged with A")

    if errors:
        raise DatasetValidationError("Counterfactual validation failed:\n" + "\n".join(errors))


def dataset_checksum(path: str | Path) -> str:
    """Return the SHA-256 checksum for reproducibility metadata."""
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
