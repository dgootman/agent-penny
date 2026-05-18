import os

import pytest
from pydantic_ai import RunContext, RunUsage

from .utils import init_chainlit_context


@pytest.mark.asyncio
async def test_tool_avatars():
    import agent_penny.agent

    await init_chainlit_context()

    agent = agent_penny.agent.create()
    ctx = RunContext(deps=None, model=agent.model, usage=RunUsage(), agent=agent)  # ty:ignore[invalid-argument-type]
    toolset = agent._get_toolset()
    tools = await toolset.get_tools(ctx)  # ty:ignore[invalid-argument-type]

    missing_avatars = [
        f"public/avatars/{tool_name}.png"
        for tool_name in tools.keys()
        if not os.path.exists(f"public/avatars/{tool_name}.png")
    ]

    assert not missing_avatars
