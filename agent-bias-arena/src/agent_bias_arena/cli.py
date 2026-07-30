"""Command-line interface for validation, execution, and saved-run analysis."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import load_config
from .dataset import load_dataset
from .runner import RunSelection, run_experiment, validate_run


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""
    parser = argparse.ArgumentParser(prog="agent-bias-arena")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-data", help="validate JSONL counterfactual pairs")
    validate.add_argument("--data", type=Path, required=True)

    run = subparsers.add_parser("run", help="run an experiment")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--scenario-id", action="append", dest="scenario_ids")
    run.add_argument("--conditions", help="comma-separated configured condition subset")
    run.add_argument("--repetition", type=int, action="append", dest="repetitions")
    run.add_argument("--dry-run", action="store_true")

    analyze = subparsers.add_parser("analyze", help="regenerate analysis from saved episodes")
    analyze.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the requested command and return a process exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "validate-data":
        scenarios = load_dataset(args.data)
        print(
            json.dumps(
                {
                    "status": "valid",
                    "scenarios": len(scenarios),
                    "pairs": len({scenario.pair_id for scenario in scenarios}),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "analyze":
        from .reporting import analyze_run

        metrics = analyze_run(args.run_dir)
        print(
            json.dumps(
                {"run_dir": str(args.run_dir.resolve()), "counts": metrics["counts"]}, indent=2
            )
        )
        return 0

    config = load_config(args.config)
    selection = RunSelection(
        scenario_ids=frozenset(args.scenario_ids) if args.scenario_ids else None,
        conditions=(
            frozenset(item.strip() for item in args.conditions.split(","))
            if args.conditions
            else None
        ),
        repetitions=frozenset(args.repetitions) if args.repetitions else None,
    )
    if args.dry_run:
        result = validate_run(config, selection)
        print(json.dumps(result.__dict__, indent=2))
        return 0
    paths, _ = run_experiment(config, selection)
    from .reporting import analyze_run

    metrics = analyze_run(paths.root)
    print(json.dumps({"run_dir": str(paths.root), "counts": metrics["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
