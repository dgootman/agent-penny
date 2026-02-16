MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

.PHONY: all
all: build test

.PHONY: build
build: sync
	uv run ruff check
	uv run mypy app.py agent_penny

.PHONY: readme
readme: README.md

README.md: app.py agent_penny/*.py agent_penny/**/*.py
	gemini -p "Update the README.md file using the update-readme skill" -m gemini-3-pro-preview --approval-mode auto_edit

.PHONY: review
review:
	gemini -p "Review the staged changes using the code-reviewer skill"

.PHONY: sync
sync:
	uv sync

.PHONY: test
test:
	uv run pytest
