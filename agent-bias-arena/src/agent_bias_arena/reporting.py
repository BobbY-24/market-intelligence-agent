"""Metric persistence, plots, and cautious Markdown reporting."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

_matplotlib_cache = Path(tempfile.gettempdir()) / "agent-bias-arena-matplotlib"
_matplotlib_cache.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from .config import load_config  # noqa: E402
from .metrics import compute_metrics  # noqa: E402
from .schemas import EpisodeRecord  # noqa: E402
from .storage import load_episodes, paths_for_existing_run  # noqa: E402

PLOT_FILES = {
    "counterfactual_flips": "counterfactual_flip_rate_by_condition.png",
    "decision_changes": "decision_change_rate_by_condition.png",
    "agreements": "initial_vs_final_agreement.png",
    "selection_rates": "selection_rate_by_group_condition.png",
    "invalid_outputs": "invalid_output_rate_by_stage.png",
}


def analyze_run(run_dir: str | Path) -> dict[str, Any]:
    """Regenerate metrics, plots, and summary from canonical saved episodes."""
    paths = paths_for_existing_run(run_dir)
    if not paths.episodes.is_file() or not paths.config.is_file():
        raise FileNotFoundError(f"Run directory lacks episodes/config artifacts: {paths.root}")
    config = load_config(paths.config)
    episodes = load_episodes(paths.episodes)
    metrics = compute_metrics(
        episodes,
        bootstrap_repetitions=config.experiment.bootstrap_repetitions,
        seed=config.experiment.seed,
    )
    paths.metrics.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    paths.plots.mkdir(exist_ok=True)
    create_plots(metrics, paths.plots)
    metadata = (
        json.loads(paths.metadata.read_text(encoding="utf-8")) if paths.metadata.is_file() else {}
    )
    config_dict = yaml.safe_load(paths.config.read_text(encoding="utf-8"))
    paths.summary.write_text(
        build_summary(config_dict, metadata, metrics, episodes), encoding="utf-8"
    )
    return metrics


def create_plots(metrics: dict[str, Any], plots_dir: Path) -> None:
    """Create the five required denominator-aware matplotlib plots."""
    records = metrics["records"]
    counterfactual_rows = []
    for record in records:
        if record["metric"] == "counterfactual_position_flip_rate":
            counterfactual_rows.append({**record, "flip_type": "candidate_position"})
        elif record["metric"] == "counterfactual_group_preference_flip_rate":
            counterfactual_rows.append({**record, "flip_type": "demographic_group_preference"})
    _grouped_bar(
        counterfactual_rows,
        plots_dir / PLOT_FILES["counterfactual_flips"],
        "Counterfactual flip rates by condition",
        group_key="condition",
        series_key="flip_type",
        ylabel="Flip rate",
    )
    _simple_bar(
        [r for r in records if r["metric"] == "decision_change_rate"],
        plots_dir / PLOT_FILES["decision_changes"],
        "Decision-change rate by interactive condition",
        "Condition",
        "Decision-change rate",
        key=lambda row: row["condition"],
    )
    _grouped_bar(
        [r for r in records if r["metric"] == "agreement_rate"],
        plots_dir / PLOT_FILES["agreements"],
        "Initial versus final agreement rate",
        group_key="condition",
        series_key="stage",
        ylabel="Agreement rate",
    )
    _grouped_bar(
        [
            r
            for r in records
            if r["metric"] == "selection_rate"
            and r.get("demographic_group") in {"group_1", "group_2"}
        ],
        plots_dir / PLOT_FILES["selection_rates"],
        "Selection rate by synthetic demographic group and condition",
        group_key="condition",
        series_key="demographic_group",
        ylabel="Selection rate",
    )
    invalid = [r for r in records if r["metric"] == "invalid_output_rate"]
    aggregated = _aggregate_invalid_by_stage(invalid)
    _simple_bar(
        aggregated,
        plots_dir / PLOT_FILES["invalid_outputs"],
        "Invalid structured-output attempt rate by stage",
        "Decision stage",
        "Invalid attempt rate",
        key=lambda row: row["stage"],
    )


def build_summary(
    config: dict[str, Any],
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    episodes: list[EpisodeRecord],
) -> str:
    """Build a self-contained cautious research summary."""
    counts = metrics["counts"]
    important = [
        record
        for record in metrics["records"]
        if record["metric"]
        in {
            "selection_rate",
            "counterfactual_position_flip_rate",
            "counterfactual_group_preference_flip_rate",
            "decision_change_rate",
            "agreement_rate",
            "peer_adoption_rate",
            "bias_amplification_flip",
            "bias_amplification_selection_gap",
            "invalid_output_rate",
        }
    ]
    lines = [
        "# Agent Bias Arena — Run Summary",
        "",
        "> **MVP warning:** This controlled synthetic experiment is not evidence of real-world "
        "discrimination and must not be used for hiring decisions about real people.",
        "",
        "## Run and configuration",
        "",
        f"- Run ID: `{metadata.get('run_id', 'unknown')}`",
        f"- Model backend/name: `{metadata.get('model_backend', 'unknown')}` / "
        f"`{metadata.get('model_name', 'unknown')}`",
        f"- Dataset checksum: `{metadata.get('dataset_checksum_sha256', 'unknown')}`",
        f"- Valid episodes: {counts['valid_episodes']} / {counts['total_episodes']}",
        f"- Invalid episodes: {counts['invalid_episodes']} / {counts['total_episodes']}",
        "",
        "```yaml",
        yaml.safe_dump(config, sort_keys=False).strip(),
        "```",
        "",
        "## Metric definitions",
        "",
    ]
    for name, definition in metrics["definitions"].items():
        lines.append(f"- **{name}**: {definition}")
    lines.extend(
        [
            "",
            "## Results",
            "",
            _metric_table(important),
            "",
            "Bootstrap intervals are percentile 95% intervals when at least two valid "
            "observations exist. Numerators and denominators show exclusions explicitly.",
            "",
            "## Relative comparisons",
            "",
        ]
    )
    amplifications = [
        row for row in metrics["records"] if row["metric"].startswith("bias_amplification")
    ]
    if amplifications:
        for row in amplifications:
            lines.append(
                f"- `{row['metric']}` ({row.get('comparison', '')}): "
                f"{_format_number(row['estimate'])}, 95% bootstrap CI "
                f"[{_format_number(row['ci_95_low'])}, {_format_number(row['ci_95_high'])}]."
            )
    else:
        lines.append("- No matched single/interactive comparison was available in this subset.")
    lines.extend(
        [
            "",
            "These differences are descriptive MVP estimates, not causal proof.",
            "",
            "## Plots",
            "",
        ]
    )
    for label, filename in PLOT_FILES.items():
        lines.append(f"- [{label.replace('_', ' ').title()}](plots/{filename})")
    lines.extend(["", "## Example transcripts", ""])
    examples = [episode for episode in episodes if episode.messages and episode.valid][:3]
    if not examples:
        lines.append("No valid interactive transcripts were available.")
    for episode in examples:
        lines.extend(
            [
                f"### `{episode.episode_id}`",
                "",
                f"Condition: `{episode.condition}`. This transcript is raw observed model output.",
                "",
            ]
        )
        for message in episode.messages:
            lines.append(f"- **{message.sender} → {message.receiver}:** {message.content}")
        if episode.manipulation:
            lines.append(
                "- **Manipulation label:** Explicit experimentally injected tie-break preference; "
                "it is not naturally emerging behavior."
            )
        lines.append("")
    lines.extend(
        [
            "## Limitations and ethical safeguards",
            "",
            "- All candidates and qualifications are fictional; the dataset contains only "
            "synthetic gender markers and cannot establish real-world discrimination.",
            "- The sample is small, prompts are simplified, and repeated observations from one "
            "model/configuration are not independent human or organizational decisions.",
            "- Local-model behavior can vary with hardware, quantization, sampling settings, and "
            "model version. Even a configured seed may not guarantee bitwise reproducibility.",
            "- The biased-peer condition is an explicitly injected research manipulation and is "
            "always labeled as such; it must not be described as spontaneous model behavior.",
            "- Raw rationales may contain biased language. Reports must distinguish observed model "
            "output from researcher interpretation.",
            "- Model outputs are not evidence about demographic groups and must never be used to "
            "make employment recommendations about real people.",
            "",
        ]
    )
    return "\n".join(lines)


def _simple_bar(
    rows: list[dict[str, Any]],
    path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    *,
    key: Any,
) -> None:
    figure, axis = plt.subplots(figsize=(8, 4.8))
    if rows:
        label_order = {
            "single": 0,
            "independent": 1,
            "interactive": 2,
            "biased_peer": 3,
            "initial": 0,
            "final": 1,
        }
        rows = sorted(
            rows,
            key=lambda row: (label_order.get(str(key(row)), 99), str(key(row))),
        )
        labels = [str(key(row)) for row in rows]
        estimates = [row["estimate"] for row in rows]
        bars = axis.bar(labels, estimates, color="#4776a8")
        for bar, row in zip(bars, rows, strict=True):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"n={row['denominator']}",
                ha="center",
                fontsize=8,
            )
    else:
        axis.text(0.5, 0.5, "No valid observations", ha="center", va="center")
    axis.set(title=title, xlabel=xlabel, ylabel=ylabel, ylim=(0, 1.15))
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _grouped_bar(
    rows: list[dict[str, Any]],
    path: Path,
    title: str,
    *,
    group_key: str,
    series_key: str,
    ylabel: str,
) -> None:
    figure, axis = plt.subplots(figsize=(9, 5))
    condition_order = {"single": 0, "independent": 1, "interactive": 2, "biased_peer": 3}
    series_order = {
        "initial": 0,
        "final": 1,
        "group_1": 0,
        "group_2": 1,
        "candidate_position": 0,
        "demographic_group_preference": 1,
    }
    groups = sorted(
        {str(row[group_key]) for row in rows},
        key=lambda value: (condition_order.get(value, 99), value),
    )
    series = sorted(
        {str(row[series_key]) for row in rows},
        key=lambda value: (series_order.get(value, 99), value),
    )
    width = 0.8 / max(len(series), 1)
    for series_index, series_value in enumerate(series):
        selected = {
            str(row[group_key]): row for row in rows if str(row[series_key]) == series_value
        }
        positions = [index - 0.4 + width / 2 + series_index * width for index in range(len(groups))]
        estimates = [selected[group]["estimate"] for group in groups]
        bars = axis.bar(positions, estimates, width=width, label=series_value.replace("_", " "))
        for bar, group in zip(bars, groups, strict=True):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.015,
                f"n={selected[group]['denominator']}",
                ha="center",
                fontsize=7,
            )
    if not rows:
        axis.text(0.5, 0.5, "No valid observations", ha="center", va="center")
    axis.set_xticks(range(len(groups)), groups)
    axis.set(title=title, xlabel="Condition", ylabel=ylabel, ylim=(0, 1.15))
    if series:
        axis.legend(
            title=series_key.replace("_", " ").title(),
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
        )
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _aggregate_invalid_by_stage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        totals[row["stage"]][0] += row["numerator"]
        totals[row["stage"]][1] += row["denominator"]
    return [
        {
            "stage": stage,
            "numerator": numerator,
            "denominator": int(denominator),
            "estimate": numerator / denominator if denominator else 0.0,
        }
        for stage, (numerator, denominator) in sorted(totals.items())
    ]


def _metric_table(records: list[dict[str, Any]]) -> str:
    rows: list[dict[str, str]] = []
    for record in records:
        group_stage = record.get("demographic_group") or record.get("stage") or "—"
        if record["metric"] == "invalid_output_rate":
            group_stage = (
                f"{record['stage']}; agent {record['agent_id']}; {record['model_backend']}"
            )
        rows.append(
            {
                "Metric": record["metric"],
                "Condition": record.get("condition", "—"),
                "Group/stage": group_stage,
                "Numerator": _format_number(record.get("numerator")),
                "Denominator": str(record["denominator"]),
                "Estimate": _format_number(record["estimate"]),
                "95% CI": (
                    f"[{_format_number(record['ci_95_low'])}, "
                    f"{_format_number(record['ci_95_high'])}]"
                ),
            }
        )
    table = pd.DataFrame.from_records(rows)
    return _markdown_table(list(table.columns), table.astype(str).values.tolist())


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def _format_number(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.3f}"
