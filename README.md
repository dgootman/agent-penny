# Agent Penny

Agent Penny is a personal AI assistant built with [Chainlit](httpss://docs.chainlit.io/) and `pydantic-ai`. It provides a conversational interface that can leverage large language models (LLMs), external tools, and your personal data to act as a powerful and context-aware assistant.

## Features

### Core Features

-   **Conversational AI**: Engage in natural, context-aware conversations powered by `pydantic-ai`.
-   **Extensible Toolset**: Easily extend the agent's capabilities with custom tools.
-   **User-Specific Persistent Memory**: The agent remembers key details from past conversations for each user, ensuring continuity and personalization.
-   **Multi-LLM Support**: Compatible with various LLM backends, including Google, OpenAI, and Anthropic (via AWS Bedrock).
-   **Conversation Starters**: Pre-defined prompts like "📅 Today's Calendar" and "✉️ Mail Summary" to help you get started.
-   **Structured Logging**: In-depth logging with `loguru` for easier debugging and monitoring.
-   **Container-Ready**: Comes with a `Dockerfile` for easy deployment.

### Integrations

-   **Google**: Securely connect your Google account to:
    -   List your Google Calendars.
    -   Read and create events from your Google Calendar.
    -   List and read your emails from Gmail.
-   **Perplexity**: (Optional) If configured, the agent can use Perplexity for powerful, up-to-date web searches.

### Tools

The agent comes equipped with the following tools:

-   **Google Calendar**: `calendar_list`, `calendar_list_events`, and `calendar_add_event` to manage your schedule.
-   **Gmail**: `email_list_messages` to access your emails.
-   **Perplexity**: `perplexity` for web searches (requires API key).
-   **Memory**: `load_memory` and `save_memory` for long-term persistence.
-   **Utility**: `current_date` to get the current date and time.

## Authentication

Agent Penny uses Google OAuth for user authentication. When you first log in, you will be asked to grant permission for the application to access your Google Calendar and Gmail in read-only mode. This is a secure process that allows the agent to work with your data without storing your credentials.

The application requests the following scopes:

-   `https://www.googleapis.com/auth/userinfo.profile`
-   `https://www.googleapis.com/auth/userinfo.email`
-   `https://www.googleapis.com/auth/gmail.readonly`
-   `https://www.googleapis.com/auth/calendar.readonly`

To grant Agent Penny access to your email and calendar, you'll need to set up OAuth.

1. Generate JWT Token for Chainlit using `chainlit create-secret`.
  - Save the secret as `CHAINLIST_AUTH_SECRET=XXXX` in `.env` or passed to chainlit as an environment variable.
2. Set up a client ID and client secret for access to your email and calendar.
  - For Google:
      1. Create a Google Application following [Google Identity Docs](https://developers.google.com/identity/protocols/oauth2). Use the `Web Application` client type. If this is your first Google Application, you'll have to provide some Branding details like App Information as well.
      2. Set Authorized JavaScript Origins as `http://localhost:8000`
      3. Set Authorized Redirect URIs as `http://localhost:8000/auth/oauth/google/callback`
      4. Under Audience - Add your own Gmail as a test user.
3. Start Agent Penny with the provided `OAUTH_GOOGLE_CLIENT_ID` and `OAUTH_GOOGLE_CLIENT_SECRET` as an environment variable.

For other OAuth providers, check out the [Chainlit OAuth docs](http://docs.chainlit.io/authentication/oauth).

## Getting Started

### Prerequisites

-   uv
-   Python 3.12
-   A Google OAuth Client ID and Secret (see `app.py` for required scopes).
-   An LLM API key (e.g., for Google, OpenAI, or AWS Bedrock).

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

## Usage

### Standalone Mode (Without Google OAuth)

Agent Penny can be run without Google OAuth for local development or if you do not require Google integrations (Calendar or Gmail). To enable standalone mode, simply omit the `OAUTH_GOOGLE_CLIENT_ID` and `OAUTH_GOOGLE_CLIENT_SECRET` environment variables. In this mode:

-   User authentication will use your system's username.
-   Google Calendar and Gmail tools will not be available.
-   Other features, such as LLM interaction, Perplexity search (if configured), and persistent memory, will function as usual.

### With Google OAuth

1.  Set the environment variables for your chosen LLM and other configurations. For example:

    **For Google Gemini:**
    ```bash
    export MODEL='google-gla:gemini-2.5-pro'
    export GOOGLE_API_KEY='your-google-api-key'
    export OAUTH_GOOGLE_CLIENT_ID='your-google-oauth-client-id'
    export OAUTH_GOOGLE_CLIENT_SECRET='your-google-oauth-client-secret'
    ```

    **For OpenAI:**
    ```bash
    export MODEL='openai:gpt-5'
    export OPENAI_API_KEY='your-openai-api-key'
    export OAUTH_GOOGLE_CLIENT_ID='your-google-oauth-client-id'
    export OAUTH_GOOGLE_CLIENT_SECRET='your-google-oauth-client-secret'
    ```

    For other providers and models, refer to the [Pydantic AI Models Documentation](https://ai.pydantic.dev/models/).

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

2.  Run the Docker container, making sure to pass all necessary environment variables:
    ```bash
    docker run -p 8000:8000 \
      -e MODEL='your-chosen-model' \
      -e GOOGLE_API_KEY='your-google-api-key' \
      -e OAUTH_GOOGLE_CLIENT_ID='your-google-oauth-client-id' \
      -e OAUTH_GOOGLE_CLIENT_SECRET='your-google-oauth-client-secret' \
      -e PERPLEXITY_API_KEY='your-perplexity-api-key' \ # Optional
      agent-penny
    ```

## Configuration

-   `MODEL`: (Required) Specifies the LLM to use. Examples: `openai:gpt-5`, `google-gla:gemini-2.5-pro`, `bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0`.
-   `OAUTH_GOOGLE_CLIENT_ID`: (Required) Your Google OAuth Client ID.
-   `OAUTH_GOOGLE_CLIENT_SECRET`: (Required) Your Google OAuth Client Secret.
-   `PERPLEXITY_API_KEY`: (Optional) Your Perplexity AI API key. If provided, enables the `perplexity` tool.
-   `LOGURU_LEVEL`: (Optional) Sets the logging level. Defaults to `DEBUG`. Set to `TRACE` for verbose event logging.
-   `DATA_DIR`: (Optional) Specifies the directory to store agent data, such as memories. Defaults to `~/.local/share/agent-penny`.

## Built With

-   [Chainlit](httpss://docs.chainlit.io/): For the web UI and chat interface.
-   [pydantic-ai](httpss://github.com/vLLM-project/pydantic-ai): For the agent and LLM interaction.
-   [Loguru](httpss://loguru.readthedocs.io/): For logging.
