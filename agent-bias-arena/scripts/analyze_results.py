#!/usr/bin/env python3
"""Thin convenience wrapper around the package analysis command."""

from __future__ import annotations

import argparse

from agent_bias_arena.reporting import analyze_run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    analyze_run(args.run_dir)


if __name__ == "__main__":
    main()
