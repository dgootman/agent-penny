from dataclasses import dataclass, field
from typing import Any, TypedDict, override

from pydantic_ai import AgentToolset, FunctionToolset
from pydantic_ai.capabilities import AbstractCapability
from tavily.async_tavily import AsyncTavilyClient  # type: ignore[import-untyped]


class TavilySearchResult(TypedDict):
    url: str
    title: str
    content: str
    score: float


class TavilySearchResponse(TypedDict):
    query: str
    results: list[TavilySearchResult]
    response_time: float
    request_id: str


@dataclass
class TavilyCapability(AbstractCapability[Any]):
    api_key: str = field(repr=False)

    def __post_init__(self):
        self.client = AsyncTavilyClient(api_key=self.api_key)

    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        toolset = FunctionToolset()
        toolset.add_function(self.tavily_search)
        return toolset

    async def tavily_search(self, query: str) -> TavilySearchResponse:
        """Execute a search query using Tavily Search."""
        return await self.client.search(query)  # ty: ignore[invalid-return-type]
