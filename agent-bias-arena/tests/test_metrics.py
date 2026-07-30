from __future__ import annotations

from agent_bias_arena.metrics import compute_metrics
from agent_bias_arena.schemas import (
    Decision,
    DecisionRecord,
    EpisodeRecord,
    MessageRecord,
    ParseAttempt,
)


def _decision(
    choice: str, stage: str, *, agent_id: str = "A", bad_attempt: bool = False
) -> DecisionRecord:
    decision = Decision(
        selected_candidate=choice,
        confidence=0.5,
        reason_codes=["skills"],
        short_rationale="Balanced evidence.",
        changed_from_initial_decision=False if stage == "final" else None,
    )
    attempts = []
    if bad_attempt:
        attempts.append(ParseAttempt(attempt=0, raw_response="bad", error="invalid JSON"))
    attempts.append(ParseAttempt(attempt=len(attempts), raw_response="{}"))
    return DecisionRecord(
        agent_id=agent_id,
        stage=stage,
        decision=decision,
        raw_response="{}",
        attempts=attempts,
        valid=True,
    )


def _episode(variant: str, choice: str, *, bad_attempt: bool = False) -> EpisodeRecord:
    demographics = {"A": "group_1", "B": "group_2"}
    if variant == "swapped":
        demographics = {"A": "group_2", "B": "group_1"}
    initial = _decision(choice, "initial")
    final = _decision(choice, "final", bad_attempt=bad_attempt)
    return EpisodeRecord(
        run_id="run",
        episode_id=f"episode-{variant}",
        scenario_id=f"scenario-{variant}",
        pair_id="pair",
        variant=variant,
        condition="single",
        repetition=0,
        seed=1,
        model_backend="mock",
        model_name="mock",
        candidate_demographics=demographics,
        candidate_pronouns={"A": "she/her", "B": "he/him"},
        agent_a_initial=initial,
        agent_a_final=final,
        latency_seconds=0,
        valid=True,
    )


def _metric(metrics, name, **dimensions):
    return next(
        record
        for record in metrics["records"]
        if record["metric"] == name
        and all(record.get(key) == value for key, value in dimensions.items())
    )


def test_counterfactual_position_and_group_flips_are_distinct() -> None:
    metrics = compute_metrics(
        [_episode("original", "A"), _episode("swapped", "A")], bootstrap_repetitions=20
    )
    position = _metric(metrics, "counterfactual_position_flip_rate", condition="single")
    group = _metric(metrics, "counterfactual_group_preference_flip_rate", condition="single")
    assert (position["numerator"], position["denominator"], position["estimate"]) == (0, 1, 0)
    assert (group["numerator"], group["denominator"], group["estimate"]) == (1, 1, 1)


def test_ties_remain_in_selection_denominators() -> None:
    episodes = [_episode("original", "TIE"), _episode("swapped", "TIE")]
    metrics = compute_metrics(episodes, bootstrap_repetitions=20)
    group_1 = _metric(metrics, "selection_rate", condition="single", demographic_group="group_1")
    ties = _metric(metrics, "selection_rate", condition="single", demographic_group="TIE")
    assert group_1["denominator"] == 2
    assert group_1["numerator"] == 0
    assert ties["numerator"] == 2


def test_invalid_output_rate_counts_repaired_attempts() -> None:
    episode = _episode("original", "A", bad_attempt=True)
    metrics = compute_metrics([episode], bootstrap_repetitions=20)
    invalid = _metric(
        metrics,
        "invalid_output_rate",
        condition="single",
        agent_id="A",
        stage="final",
        model_backend="mock",
    )
    assert invalid["numerator"] == 1
    assert invalid["denominator"] == 2
    assert invalid["estimate"] == 0.5


def test_change_agreement_and_peer_adoption_metrics() -> None:
    episode = EpisodeRecord(
        run_id="run",
        episode_id="interactive-original",
        scenario_id="scenario-original",
        pair_id="pair",
        variant="original",
        condition="interactive",
        repetition=0,
        seed=1,
        model_backend="mock",
        model_name="mock",
        candidate_demographics={"A": "group_1", "B": "group_2"},
        candidate_pronouns={"A": "she/her", "B": "he/him"},
        agent_a_initial=_decision("A", "initial", agent_id="A"),
        agent_b_initial=_decision("B", "initial", agent_id="B"),
        messages=[
            MessageRecord(
                round=1,
                kind="argument",
                sender="A",
                receiver="B",
                content="I recommend A.",
                advocated_candidate="A",
            ),
            MessageRecord(
                round=1,
                kind="response",
                sender="B",
                receiver="A",
                content="I recommend B.",
                advocated_candidate="B",
            ),
        ],
        agent_a_final=_decision("B", "final", agent_id="A"),
        agent_b_final=_decision("B", "final", agent_id="B"),
        latency_seconds=0,
        valid=True,
    )
    metrics = compute_metrics([episode], bootstrap_repetitions=20)
    assert _metric(metrics, "decision_change_rate", condition="interactive")["estimate"] == 0.5
    assert (
        _metric(metrics, "agreement_rate", condition="interactive", stage="initial")["estimate"]
        == 0
    )
    assert (
        _metric(metrics, "agreement_rate", condition="interactive", stage="final")["estimate"] == 1
    )
    assert _metric(metrics, "peer_adoption_rate", condition="interactive")["estimate"] == 0.5
