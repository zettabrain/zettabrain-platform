.PHONY: install dev serve setup test lint

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

serve:
	python -m zettabrain_platform.cli serve

setup:
	python -m zettabrain_platform.cli setup

test:
	pytest tests/ -v

lint:
	ruff check zettabrain_platform/ tests/
