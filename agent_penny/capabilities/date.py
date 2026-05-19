from dataclasses import dataclass
from datetime import datetime
from typing import Any, override
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_ai import AgentToolset, FunctionToolset, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability

from agent_penny import user_data


async def get_timezone_setting() -> str | None:
    user_settings = user_data.load_settings()
    return user_settings.get("timezone")


async def set_timezone_setting(timezone: str) -> None:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as e:
        raise ModelRetry(str(e)) from e

    user_settings = user_data.load_settings()
    user_settings["timezone"] = timezone
    user_data.save_settings(user_settings)


async def current_time(timezone: str | None = None) -> str:
    """
    Get the current date and time

    Args:
        timezone: Timezone in IANA format (e.g. America/Vancouver)
    """

    if not timezone:
        timezone = await get_timezone_setting()

    return datetime.now(tz=ZoneInfo(timezone) if timezone else None).isoformat()


@dataclass
class DateTimeCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        toolset = FunctionToolset()
        toolset.add_function(current_time)
        toolset.add_function(get_timezone_setting)
        toolset.add_function(set_timezone_setting)
        return toolset

    @override
    def get_instructions(self):
        async def _get_instructions(ctx: RunContext[Any]) -> str | None:
            # Timezone must be provided for time instruction
            timezone = await get_timezone_setting()
            if not timezone:
                return None

            time = await current_time(timezone)

            return f"The user's preferred timezone is {timezone} and the current time is {time}"

        return _get_instructions
