.PHONY: build

build:
	ruff check
	mypy app.py agent_penny
