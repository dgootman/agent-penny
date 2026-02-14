.PHONY: release build review readme sync

release: build readme

sync:
	uv sync

build: sync
	uv run ruff check
	uv run mypy app.py agent_penny

review:
	gemini -p "Review the staged changes using the code-reviewer skill"

readme: README.md

README.md: app.py agent_penny/*.py agent_penny/**/*.py
	gemini -p "Update the README.md file using the update-readme skill" -m gemini-3-pro-preview --approval-mode auto_edit
