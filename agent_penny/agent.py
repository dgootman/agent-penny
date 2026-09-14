from typing import Any, Callable

from exa_py import AsyncExa
from loguru import logger
from pydantic_ai import AbstractToolset, Agent, Tool
from pydantic_ai.capabilities import AbstractCapability, PrefixTools
from pydantic_ai.models import Model
from pydantic_ai_harness import ExaSearch
from pydantic_ai_harness.memory import FileStore, Memory

from agent_penny import user_data
from agent_penny.available_models import resolve_model
from agent_penny.capabilities.compaction import CompactionCapability
from agent_penny.capabilities.date import DateTimeCapability
from agent_penny.capabilities.duckduckgo import DuckDuckGoCapability
from agent_penny.capabilities.google_maps import GoogleMapsCapability
from agent_penny.capabilities.images import ImageGenerationCapability
from agent_penny.capabilities.perplexity import PerplexityCapability
from agent_penny.capabilities.scheduling import SchedulingCapability
from agent_penny.capabilities.skills import SkillsCapability
from agent_penny.capabilities.tavily import TavilyCapability
from agent_penny.capabilities.telegram import TelegramCapability
from agent_penny.capabilities.web import WebFetchCapability
from agent_penny.chainlit_utils import get_user
from agent_penny.settings import settings

# default_model can be overriden for tests
default_model: str | Model | None = settings.MODEL


def create() -> Agent:
    user = get_user()
    user_settings = user_data.load_settings()

    tools: list[Callable[..., Any] | Tool] = []

    toolsets: list[AbstractToolset[Any]] = []

    if user.metadata.get("provider") == "google":
        from agent_penny.providers.google import GoogleProvider

        toolsets.append(GoogleProvider().toolset)

    model = user_settings.get("model") or default_model

    model = resolve_model(model)

    capabilities: list[AbstractCapability] = [
        CompactionCapability(),
        DateTimeCapability(),
        GoogleMapsCapability(),
        ImageGenerationCapability(),
        Memory(FileStore(user_data.path(".agent-memory"))),
        SchedulingCapability(),
        SkillsCapability(),
        TelegramCapability(),
        WebFetchCapability(),
    ]

    if exa_api_key := user_settings.get("exa_api_key") or settings.EXA_API_KEY:
        capabilities.append(
            PrefixTools(
                ExaSearch(client=AsyncExa(api_key=exa_api_key)),
                "exa",
            )
        )

    if tavily_api_key := user_settings.get("tavily_api_key") or settings.TAVILY_API_KEY:
        capabilities.append(TavilyCapability(api_key=tavily_api_key))

    if (
        perplexity_api_key := user_settings.get("perplexity_api_key")
        or settings.PERPLEXITY_API_KEY
    ):
        capabilities.append(PerplexityCapability(api_key=perplexity_api_key))

    if (
        user_settings.get("duckduckgo_search_enabled")
        or settings.DUCKDUCKGO_SEARCH_ENABLED
    ):
        capabilities.append(DuckDuckGoCapability())

    logger.debug(
        "Creating agent",
        model=str(model),
        tools=[str(t) for t in tools],
        toolsets=toolsets,
        capabilities=[type(c).__name__ for c in capabilities],
    )

    return Agent(
        model,
        tools=tools,
        toolsets=toolsets,
        capabilities=capabilities,
    )
