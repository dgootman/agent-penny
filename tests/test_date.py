from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelRetry,
    TextPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .utils import init_chainlit_context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timezone",
    [
        ("America/Vancouver"),
        ("America/New_York"),
        ("Europe/London"),
        ("Asia/Tel_Aviv"),
        ("Australia/Sydney"),
    ],
)
async def test_get_instructions(timezone: str, tmp_user_data):
    import agent_penny.capabilities.date as date
    from agent_penny.capabilities.date import DateTimeCapability

    await init_chainlit_context()

    await date.set_timezone_setting(timezone)
    timezone_setting = await date.get_timezone_setting()
    assert timezone_setting == timezone

    requests: list[ModelRequest] = []

    async def model_function(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        message = messages[-1]
        assert isinstance(message, ModelRequest)
        requests.append(message)
        return ModelResponse(parts=[TextPart("Hello")])

    agent = Agent(FunctionModel(model_function), capabilities=[DateTimeCapability()])

    await agent.run("Hello")

    offset_delta = ZoneInfo(timezone).utcoffset(datetime.now())
    assert offset_delta
    positive_offset = offset_delta.days >= 0
    if not positive_offset:
        offset_delta = -offset_delta
    offset = ("+" if positive_offset else "-") + str(offset_delta)[:-3].rjust(5, "0")

    [request] = requests
    assert request.instructions
    assert timezone in request.instructions
    assert offset in request.instructions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timezone",
    [
        ("Vancouver"),
        ("Asia/Vancouver"),
        ("London"),
        ("America/London"),
        ("Tel Aviv"),
        ("Asia/TelAviv"),
        ("Europe/Tel_Aviv"),
    ],
)
async def test_set_timezone_setting_invalid(timezone: str):
    import agent_penny.capabilities.date as date

    await init_chainlit_context()

    with pytest.raises(ModelRetry):
        await date.set_timezone_setting(timezone)
