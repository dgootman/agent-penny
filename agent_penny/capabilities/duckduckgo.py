from dataclasses import dataclass
from typing import Any, override

from pydantic_ai import AgentToolset, FunctionToolset
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool


@dataclass
class DuckDuckGoCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return FunctionToolset([duckduckgo_search_tool()])
