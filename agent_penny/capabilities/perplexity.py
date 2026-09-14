from dataclasses import dataclass, field
from typing import Any, override

from perplexity import AsyncPerplexity
from perplexity.types import SearchCreateResponse
from pydantic_ai import AgentToolset, FunctionToolset
from pydantic_ai.capabilities import AbstractCapability


@dataclass
class PerplexityCapability(AbstractCapability[Any]):
    api_key: str = field(repr=False)

    def __post_init__(self):
        self.client = AsyncPerplexity(api_key=self.api_key)

    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        toolset = FunctionToolset()
        toolset.add_function(self.perplexity)
        return toolset

    async def perplexity(self, query: str) -> SearchCreateResponse:
        """Execute a search query using Tavily Search."""
        return await self.client.search.create(query=query)
