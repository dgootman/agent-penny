import os

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .utils import init_chainlit_context


@pytest.mark.asyncio
async def test_tool_avatars():
    import agent_penny.agent

    await init_chainlit_context()

    agent = agent_penny.agent.create()
    tool_names: list[str] = []

    async def model_function(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        tool_names.extend(tool.name for tool in info.function_tools)
        return ModelResponse(parts=[TextPart("Done")])

    with agent.override(model=FunctionModel(model_function)):
        await agent.run("List the available tools.")

    missing_avatars = [
        f"public/avatars/{tool_name}.png"
        for tool_name in tool_names
        if not any(
            os.path.exists(f"public/avatars/{tool_name}.{extension}")
            for extension in ["png", "svg"]
        )
    ]

    assert not missing_avatars
