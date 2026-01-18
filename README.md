# Agent Penny

Agent Penny is a personal AI assistant built with [Chainlit](https://docs.chainlit.io/) and `pydantic-ai`. It provides a conversational interface that can leverage large language models (LLMs) and custom tools.

## Features

- Conversational AI agent powered by `pydantic-ai`.
- Extensible with custom tools (includes `current_date`, `load_memory`, and `save_memory` tools).
- Persistent memory to retain key details from past conversations.
- Supports various LLM backends (Bedrock, Google, OpenAI).
- Structured logging with `loguru`.
- Ready for containerization with Docker.

## Getting Started

### Prerequisites

- uv
- Python 3.12
- An LLM API key (e.g., for Google, OpenAI, or AWS Bedrock)

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/dgootman/agent-penny.git
    cd agent-penny
    ```

2.  Create a virtual environment and install the Python dependencies:
    ```bash
    uv venv
    uv pip install -r requirements.txt
    ```

3. Finally, `source` the `.venv`.
    ```bash
    source .venv/bin/activate
    ```

## Usage

1.  Set the environment variables for your chosen LLM. For example:

    **For OpenAI:**
    ```bash
    export MODEL='openai:gpt-5'
    export OPENAI_API_KEY='your-openai-api-key'
    ```

    **For Google Gemini:**
    ```bash
    export MODEL='google-gla:gemini-2.5-pro'
    export GOOGLE_API_KEY='your-google-api-key'
    ```

    **For AWS Bedrock:**
    ```bash
    export MODEL='bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0'
    export AWS_PROFILE='your-aws-profile'
    export AWS_DEFAULT_REGION='us-east-1'
    ```

    For other providers and models, refer to the [Pydantic AI Models Documentation](https://ai.pydantic.dev/models/). The format is generally `provider:model-name`.

2.  Run the application:
    ```bash
    chainlit run -w app.py
    ```

3.  Open your web browser and navigate to `http://localhost:8000`.

## Docker

You can also build and run the application using Docker.

1.  Build the Docker image:
    ```bash
    docker build -t agent-penny .
    ```

2.  Run the Docker container, making sure to pass the necessary environment variables:
    ```bash
    docker run -p 8000:8000 \
      -e MODEL='your-chosen-model' \
      -e GOOGLE_API_KEY='your-google-api-key' \
      agent-penny
    ```

## Configuration

-   `MODEL`: (Required) Specifies the LLM to use. Examples: `openai:gpt-5`, `google-gla:gemini-2.5-pro`, `bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0`.
-   `LOGURU_LEVEL`: (Optional) Sets the logging level. Defaults to `DEBUG`. Set to `TRACE` for verbose event logging.
-   `DATA_DIR`: (Optional) Specifies the directory to store agent data, such as memories. Defaults to `~/.local/share/agent-penny`.

## Built With

-   [Chainlit](https://docs.chainlit.io/): For the web UI and chat interface.
-   [pydantic-ai](https://github.com/pydantic/pydantic-ai): For the agent and LLM interaction.
-   [Loguru](https://loguru.readthedocs.io/): For logging.
