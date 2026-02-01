---
name: update-readme
description: Generates or updates a README.md file based on the application's functionality. Use when the user wants to generate or update the README.md file to reflect the current state of the application.
---

# Update README

You are an expert at analyzing a codebase and generating or updating a comprehensive `README.md` file that describes the application's functionality.

When asked to update the README, follow this workflow:

1.  **Analyze the codebase**:
    *   Use the `glob` tool to find all relevant source code files (e.g., `app.py`, `agent_penny/**/*.py`).
    *   Use the `read_file` tool to read the contents of these files.

2.  **Summarize the functionality**:
    *   Based on the code, determine the application's purpose, main features, and how to run it.
    *   Pay attention to the dependencies listed in `pyproject.toml` or `requirements.txt` if they exist.

3.  **Read the existing README.md**:
    *   Use the `read_file` tool to read the current `README.md` file.

4.  **Generate updated sections**:
    *   Based on your analysis, generate the content for the following sections:
        *   Project Title
        *   High-level description
        *   Features
        *   Getting Started
        *   Usage
        *   Configuration

5.  **Update the README.md**:
    *   For each generated section, use the `replace` tool to update the corresponding section in the `README.md` file.
    *   If a section does not exist, use the `replace` tool to add it to the `README.md` file in a logical location.
    *   **Do not overwrite the entire file.** Only update the relevant sections.
