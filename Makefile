.PHONY: release build review readme

release: build readme

build:
	ruff check
	mypy app.py agent_penny

review:
	gemini -p "Review the staged changes using the code-reviewer skill"

readme: README.md

README.md: app.py agent_penny/*.py agent_penny/**/*.py
	gemini -p "Update the README.md file using the update-readme skill" -m gemini-3-pro-preview --approval-mode auto_edit
