.PHONY: build review

build:
	ruff check
	mypy app.py agent_penny

review:
	gemini -p "Review the staged changes using the code-reviewer skill"
