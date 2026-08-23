"""Models offered in Agent Penny's settings UI."""

import genai_prices.data
from pydantic_ai.models import Model

from agent_penny.models.codex import CodexOpenAIResponsesModel

MODEL_ENV_VARS_BY_PROVIDER = {
    "anthropic": "ANTHROPIC_API_KEY",
    # Bedrock uses AWS credentials, which have different ways of being provisioned.
    "bedrock": "BEDROCK_ENABLE",
    "google": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-codex": "OPENAI_CODEX_ENABLE",
}

AVAILABLE_MODELS_BY_PROVIDER = {
    "anthropic": (  # https://platform.claude.com/docs/en/about-claude/models/overview
        "anthropic:claude-fable-5",
        "anthropic:claude-opus-5",
        "anthropic:claude-sonnet-5",
        "anthropic:claude-haiku-4-5",
    ),
    "bedrock": (  # https://platform.claude.com/docs/en/about-claude/models/overview
        "bedrock:us.anthropic.claude-fable-5",
        "bedrock:us.anthropic.claude-opus-5",
        "bedrock:us.anthropic.claude-sonnet-5",
        "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ),
    "google": (  # https://ai.google.dev/gemini-api/docs/models
        "google:gemini-3.7-flash",
        "google:gemini-3.6-flash",
        "google:gemini-3.5-flash",
        "google:gemini-3.5-flash-lite",
        "google:gemini-3.1-pro-preview",
        "google:gemini-3.1-flash-lite",
        "google:gemini-3-flash-preview",
        "google:gemini-2.5-pro",
        "google:gemini-2.5-flash",
    ),
    "openai": (  # https://developers.openai.com/api/docs/models/all
        "openai:gpt-5.6-sol",
        "openai:gpt-5.6-terra",
        "openai:gpt-5.6-luna",
        "openai:gpt-5.5",
        "openai:gpt-5.4",
        "openai:gpt-5.4-mini",
        "openai:gpt-5.4-nano",
    ),
    "openai-codex": (  # https://developers.openai.com/api/docs/models/all
        "openai-codex:gpt-5.6-sol",
        "openai-codex:gpt-5.6-terra",
        "openai-codex:gpt-5.6-luna",
        "openai-codex:gpt-5.5",
        "openai-codex:gpt-5.4",
        "openai-codex:gpt-5.4-mini",
    ),
}

AVAILABLE_MODELS = tuple(
    model for models in AVAILABLE_MODELS_BY_PROVIDER.values() for model in models
)

PROVIDER_ALIASES = {
    "bedrock": "aws",
    "google-gla": "google",
    "openai-codex": "openai",
}


def resolve_model(model: str | Model | None) -> str | Model | None:
    """Translate a UI model name into a model understood by Pydantic AI."""
    if not isinstance(model, str) or ":" not in model:
        return model

    provider, model_id = model.split(":", 1)
    if provider == "openai":
        return f"openai-responses:{model_id}"
    if provider == "google-gla":
        return f"google:{model_id}"
    if provider == "openai-codex":
        return CodexOpenAIResponsesModel(model_id)
    return model


def get_context_window(model: str | Model | None) -> int | None:
    if not model:
        return None
    elif isinstance(model, str):
        if ":" not in model:
            return None
        provider_id, model_id = model.split(":", 1)
    else:
        if not model.provider:
            return None
        provider_id, model_id = (model.provider.name, model.model_name)

    provider_id = PROVIDER_ALIASES.get(provider_id, provider_id)

    provider_info = next(
        (p for p in genai_prices.data.providers if p.id == provider_id), None
    )

    if not provider_info:
        return None

    model_info = provider_info.find_model(model_id)
    if not model_info:
        return None

    return model_info.context_window
