from typing import Any, Callable

from loguru import logger
from pydantic_ai import AbstractToolset, Agent, Tool
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic_ai.models import Model

from agent_penny import user_data
from agent_penny.capabilities.date import DateTimeCapability
from agent_penny.capabilities.images import ImageGenerationCapability
from agent_penny.capabilities.scheduling import SchedulingCapability
from agent_penny.capabilities.skills import SkillsCapability
from agent_penny.capabilities.telegram import TelegramCapability
from agent_penny.capabilities.web import WebFetchCapability
from agent_penny.chainlit_utils import get_user
from agent_penny.models.codex import CodexOpenAIResponsesModel
from agent_penny.settings import settings
from agent_penny.tools.memory import MemoryProvider
from agent_penny.tools.perplexity import perplexity
from agent_penny.tools.tavily_search import tavily_search

# default_model can be overriden for tests
default_model: str | Model | None = settings.MODEL


def create() -> Agent:
    user = get_user()
    user_settings = user_data.load_settings()

    tools: list[Callable[..., Any] | Tool] = []

    toolsets: list[AbstractToolset[Any]] = []

    memory = MemoryProvider()
    toolsets.append(memory.toolset)

    if user.metadata.get("provider") == "google":
        from agent_penny.providers.google import GoogleProvider

        toolsets.append(GoogleProvider().toolset)

    if settings.PERPLEXITY_API_KEY:
        tools.append(perplexity)

    if settings.TAVILY_API_KEY:
        tools.append(tavily_search)

    if settings.DUCKDUCKGO_SEARCH_ENABLED:
        tools.append(duckduckgo_search_tool())

    model = user_settings.get("model") or default_model

    if isinstance(model, str) and ":" in model:
        provider, model_id = model.split(":", 1)
        if provider == "openai":
            model = f"openai-responses:{model_id}"
        elif provider == "openai-codex":
            model = CodexOpenAIResponsesModel(model_id)

    logger.debug(
        "Creating agent",
        model=str(model),
        tools=[str(t) for t in tools],
        toolsets=toolsets,
    )

    return Agent(
        model,
        tools=tools,
        toolsets=toolsets,
        capabilities=[
            DateTimeCapability(),
            ImageGenerationCapability(),
            SchedulingCapability(),
            SkillsCapability(),
            TelegramCapability(),
            WebFetchCapability(),
        ],
        system_prompt=[
            f"You know the following from previous conversations: {memory.load_memory()}"
        ],
    )
