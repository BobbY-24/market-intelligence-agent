PYTHON ?= python3

.PHONY: install test lint validate-data mock-run run

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

validate-data:
	$(PYTHON) -m agent_bias_arena.cli validate-data --data data/hiring_counterfactual_pairs.jsonl

mock-run:
	$(PYTHON) -m agent_bias_arena.cli run --config configs/mock.yaml

run:
	$(PYTHON) -m agent_bias_arena.cli run --config configs/mvp.yaml
