import os
from typing import TypedDict

from pydantic_ai import ModelSettings
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.bedrock import BedrockModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

default_model = os.environ["MODEL"]
default_thinking = os.environ.get("THINKING") == "true"


class AgentConfig(TypedDict):
    model: str
    model_settings: ModelSettings | None


def agent_config(
    model: str | None = None,
    thinking: bool | None = None,
) -> AgentConfig:
    model = model or default_model
    thinking = thinking if thinking is not None else default_thinking

    model_settings: ModelSettings | None = None

    if thinking:
        # See: https://ai.pydantic.dev/thinking/
        # TODO: Make model settings for thinking configurable
        llm_provider, model_id = model.split(":", 1)

        if llm_provider == "anthropic":
            model_settings = AnthropicModelSettings(
                anthropic_thinking={"type": "enabled", "budget_tokens": 1024},
            )
        elif llm_provider == "bedrock":
            if model_id.startswith("us.anthropic."):
                model_settings = BedrockModelSettings(
                    bedrock_additional_model_requests_fields={
                        "thinking": {"type": "enabled", "budget_tokens": 4000}
                    }
                )
            else:
                raise ValueError(
                    f"Thinking is not supported for Bedrock model: {model_id}"
                )
        elif llm_provider == "google-gla":
            model_settings = GoogleModelSettings(
                google_thinking_config={"include_thoughts": True}
            )
        elif llm_provider == "openai":
            # Upgrade to the OpenAI Responses API: https://platform.openai.com/docs/guides/migrate-to-responses
            model = f"openai-responses:{model_id}"
            model_settings = OpenAIResponsesModelSettings(
                openai_reasoning_effort="low",
                openai_reasoning_summary="detailed",
            )
        else:
            raise ValueError(f"Thinking is not supported for provider: {llm_provider}")

    return {
        "model": model,
        "model_settings": model_settings,
    }
