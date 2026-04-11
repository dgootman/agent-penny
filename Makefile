MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

.PHONY: all
all: build test

.PHONY: build
build: sync lint format typecheck

.PHONY: lint
lint:
	uv run ruff check

.PHONY: format
format:
	uv run ruff format --check

.PHONY: typecheck
typecheck:
	uv run ty check
	uv run mypy app.py agent_penny

.PHONY: dev
dev: sync
	uv run chainlit run -w app.py

# Instrument the app test to identify startup bottlenecks
.PHONY: instrument
instrument:
	uv run pyinstrument -m pytest -o addopts= tests/test_app.py

.PHONY: readme
readme: README.md

README.md: app.py agent_penny/*.py agent_penny/**/*.py
	gemini -i "Update the README.md file using the update-readme skill" -m gemini-3-pro-preview --approval-mode auto_edit

.PHONY: review
review:
	gemini -i "Review the staged changes using the code-reviewer skill"

.PHONY: sync
sync:
	uv sync

.PHONY: test
test:
	uv run pytest
