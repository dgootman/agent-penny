import os
from typing import Callable, TypedDict

from loguru import logger
from pydantic_ai import AbstractToolset, Agent, ModelSettings
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.bedrock import BedrockModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from agent_penny.chainlit_utils import get_user
from agent_penny.tools.date import current_date
from agent_penny.tools.memory import MemoryProvider
from agent_penny.tools.perplexity import perplexity
from agent_penny.tools.tavily_search import tavily_search
from agent_penny.tools.web import web_fetch

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


def create() -> Agent:
    user = get_user()

    tools: list[Callable] = [current_date, web_fetch]

    toolsets: list[AbstractToolset] = []

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

    config = agent_config()

    logger.debug(
        "Creating agent",
        **config,
        tools=[str(t) for t in tools],
        toolsets=toolsets,
    )

    return Agent(
        **config,
        tools=tools,
        toolsets=toolsets,
        system_prompt=[
            f"You know the following from previous conversations: {memory.load_memory()}"
        ],
    )
