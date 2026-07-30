from __future__ import annotations

from copy import deepcopy

import pytest

from agent_bias_arena.dataset import DatasetValidationError, validate_counterfactual_pairs


def test_dataset_contains_twenty_valid_pairs(scenarios) -> None:
    assert len(scenarios) == 40
    assert len({scenario.pair_id for scenario in scenarios}) == 20


def test_qualification_change_fails_pair_validation(scenarios) -> None:
    pair = [deepcopy(item) for item in scenarios if item.pair_id == "hiring_001"]
    swapped = next(item for item in pair if item.variant == "swapped")
    swapped.candidate_a.qualifications["experience_years"] = 99
    with pytest.raises(DatasetValidationError, match="qualifications changed"):
        validate_counterfactual_pairs(pair)


def test_demographic_marker_must_be_exchanged(scenarios) -> None:
    pair = [deepcopy(item) for item in scenarios if item.pair_id == "hiring_001"]
    original = next(item for item in pair if item.variant == "original")
    swapped = next(item for item in pair if item.variant == "swapped")
    swapped.candidate_a.pronouns = original.candidate_a.pronouns
    with pytest.raises(DatasetValidationError, match="pronouns were not exchanged"):
        validate_counterfactual_pairs(pair)


def test_incomplete_and_duplicate_pairs_are_rejected(scenarios) -> None:
    original = deepcopy(
        next(item for item in scenarios if item.scenario_id == "hiring_001_original")
    )
    with pytest.raises(DatasetValidationError, match="expected exactly"):
        validate_counterfactual_pairs([original])
    with pytest.raises(DatasetValidationError, match="duplicate scenario_id"):
        validate_counterfactual_pairs([original, deepcopy(original)])
