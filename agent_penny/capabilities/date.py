from dataclasses import dataclass
from datetime import datetime
from typing import Any, override
from zoneinfo import ZoneInfo

from pydantic_ai import AgentToolset, FunctionToolset
from pydantic_ai.capabilities import AbstractCapability

toolset = FunctionToolset()


# NOTE: This should be an instruction rather than a tool, but it requires the user's timezone
@toolset.tool_plain()
def current_time(timezone: str | None = None) -> str:
    """
    Get the current date and time

    Args:
        timezone: Timezone in IANA format (e.g. America/Vancouver)
    """
    return datetime.now(tz=ZoneInfo(timezone) if timezone else None).isoformat()


@dataclass
class DateTimeCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return toolset
