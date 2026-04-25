import os
from typing import Any, Callable, TypedDict

from loguru import logger
from pydantic_ai import AbstractToolset, Agent, ModelSettings, Tool
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.bedrock import BedrockModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from agent_penny import user_data
from agent_penny.capabilities.skills import SkillsCapability
from agent_penny.capabilities.telegram import TelegramCapability
from agent_penny.chainlit_utils import get_user
from agent_penny.tools.date import current_date
from agent_penny.tools.memory import MemoryProvider
from agent_penny.tools.perplexity import perplexity
from agent_penny.tools.tavily_search import tavily_search
from agent_penny.tools.web import web_fetch

# default_model can be overriden for tests
default_model: str | Model = os.environ["MODEL"]
default_thinking = os.environ.get("THINKING") == "true"


class AgentConfig(TypedDict):
    model: str | Model
    model_settings: ModelSettings | None


def agent_config(
    requested_model: str | None = None,
    thinking: bool | None = None,
) -> AgentConfig:
    model = requested_model or default_model
    thinking = thinking if thinking is not None else default_thinking

    model_settings: ModelSettings | None = None

    provider, model_id = (
        model.split(":", 1)
        if isinstance(model, str)
        else (model.system, model.model_name)
    )

    if thinking:
        # See: https://ai.pydantic.dev/thinking/
        # TODO: Make model settings for thinking configurable
        if provider == "anthropic":
            model_settings = AnthropicModelSettings(
                anthropic_thinking={"type": "enabled", "budget_tokens": 1024},  # type: ignore[ty:invalid-argument-type]
            )
        elif provider == "bedrock":
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
        elif provider == "google-gla":
            model_settings = GoogleModelSettings(
                google_thinking_config={"include_thoughts": True}
            )
        elif provider == "openai":
            # Upgrade to the OpenAI Responses API: https://platform.openai.com/docs/guides/migrate-to-responses
            model = f"openai-responses:{model_id}"
            model_settings = OpenAIResponsesModelSettings(
                openai_reasoning_effort="low",
                openai_reasoning_summary="detailed",
            )
        else:
            raise ValueError(f"Thinking is not supported for provider: {provider}")

    return {
        "model": model,
        "model_settings": model_settings,
    }


def create() -> Agent:
    user = get_user()
    settings = user_data.load_settings()

    tools: list[Callable[..., Any] | Tool] = [current_date, web_fetch]

    toolsets: list[AbstractToolset[Any]] = []

    memory = MemoryProvider()
    toolsets.append(memory.toolset)

    if user.metadata.get("provider") == "google":
        from agent_penny.providers.google import GoogleProvider

        provider = GoogleProvider()
        toolsets.append(provider.toolset)
        # await cl.Message(provider.credentials.to_json()).send()

    if "PERPLEXITY_API_KEY" in os.environ:
        tools.append(perplexity)

    if "TAVILY_API_KEY" in os.environ:
        tools.append(tavily_search)

    if os.environ.get("DUCKDUCKGO_SEARCH_ENABLED") == "true":
        tools.append(duckduckgo_search_tool())

    config = agent_config(settings.get("model"), settings.get("thinking"))

    logger.debug(
        "Creating agent",
        model=str(config["model"]),
        model_settings=config["model_settings"],
        tools=[str(t) for t in tools],
        toolsets=toolsets,
    )

    return Agent(
        **config,
        tools=tools,
        toolsets=toolsets,
        capabilities=[
            SkillsCapability(),
            TelegramCapability(),
        ],
        system_prompt=[
            f"You know the following from previous conversations: {memory.load_memory()}"
        ],
    )
