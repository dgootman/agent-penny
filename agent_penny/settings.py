from pydantic_ai.settings import ThinkingLevel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MODEL: str | None = None
    THINKING: ThinkingLevel = "medium"

    OAUTH_GOOGLE_CLIENT_ID: str | None = None

    ANTHROPIC_API_KEY: str | None = None
    BEDROCK_ENABLE: bool | None = None
    GOOGLE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_CODEX_ENABLE: bool | None = None

    WHISPER_MODEL: str | None = None

    CONVERSATION_HISTORY_ENABLED: bool = False

    PERPLEXITY_API_KEY: str | None = None
    TAVILY_API_KEY: str | None = None
    DUCKDUCKGO_SEARCH_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: str | None = None

    SCHEDULING_DISABLED: bool | None = None

    OTEL_SERVICE_NAME: str = "agent-penny"
    LOGFIRE_SEND_TO_LOGFIRE: bool = False


settings = Settings()
