from __future__ import annotations

import json

from agent_bias_arena.config import load_config
from agent_bias_arena.reporting import PLOT_FILES, analyze_run
from agent_bias_arena.runner import RunSelection, run_experiment, validate_run


def test_mock_seeded_behavior_is_deterministic(project_root, tmp_path) -> None:
    config = load_config(project_root / "configs/mock.yaml")
    config.output.root_dir = tmp_path
    selection = RunSelection(
        scenario_ids=frozenset({"hiring_001_original", "hiring_001_swapped"}),
        conditions=frozenset({"single"}),
        repetitions=frozenset({0}),
    )
    first_paths, first = run_experiment(config, selection)
    second_paths, second = run_experiment(config, selection)
    assert first[0].agent_a_final.decision == second[0].agent_a_final.decision
    assert first[0].agent_a_final.decision == first[1].agent_a_final.decision
    assert first_paths.root != second_paths.root


def test_complete_mock_run_creates_all_artifacts(project_root, tmp_path) -> None:
    config = load_config(project_root / "configs/mock.yaml")
    config.output.root_dir = tmp_path
    dry_run = validate_run(config)
    assert dry_run.expected_episodes == 160
    paths, episodes = run_experiment(config)
    metrics = analyze_run(paths.root)
    assert len(episodes) == 160
    assert metrics["counts"]["invalid_episodes"] == 0
    for path in (
        paths.config,
        paths.metadata,
        paths.episodes,
        paths.decisions,
        paths.transcripts,
        paths.invalid_outputs,
        paths.metrics,
        paths.summary,
    ):
        assert path.is_file()
    assert all((paths.plots / filename).is_file() for filename in PLOT_FILES.values())
    metadata = json.loads(paths.metadata.read_text())
    assert metadata["number_of_total_episodes"] == 160
    assert "MVP warning" in paths.summary.read_text()


def test_mock_run_retains_and_counts_repaired_malformed_output(project_root, tmp_path) -> None:
    config = load_config(project_root / "configs/mock.yaml")
    config.output.root_dir = tmp_path
    config.model.mock_malformed_first_attempt = True
    selection = RunSelection(
        scenario_ids=frozenset({"hiring_001_original"}),
        conditions=frozenset({"single"}),
        repetitions=frozenset({0}),
    )
    paths, _ = run_experiment(config, selection)
    metrics = analyze_run(paths.root)
    failures = [line for line in paths.invalid_outputs.read_text().splitlines() if line]
    assert len(failures) == 1
    invalid = next(
        row
        for row in metrics["records"]
        if row["metric"] == "invalid_output_rate" and row["stage"] == "initial"
    )
    assert invalid["numerator"] == 1
    assert invalid["denominator"] == 2
