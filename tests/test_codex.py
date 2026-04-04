import os
import re
import webbrowser
from typing import Any

import pytest
from loguru import logger
from pydantic_ai import Agent, AgentRunResultEvent

from tests.utils import init_chainlit_context

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENAI_CODEX_ENABLE") != "true", reason="OpenAI Codex not enabled"
)


@pytest.mark.asyncio
async def test_codex_agent(capsys: pytest.CaptureFixture[str]):
    from agent_penny.models.codex import CodexOpenAIResponsesModel

    async def emit_mock(event: str, data: Any):
        logger.debug(f"Event emitted: {dict(event=event, data=data)}")
        if event == "new_message":
            output: str = data["output"]
            if output.startswith("To continue, follow these steps:"):
                with capsys.disabled():
                    print(output)
                    url_match = re.search(r"https://.*/device", output)
                    if url_match:
                        webbrowser.open(url_match.group(0))

    await init_chainlit_context(emit_mock)

    agent = Agent(model=CodexOpenAIResponsesModel("gpt-5.4"))

    result = None
    async for event in agent.run_stream_events("Who is Miss Moneypenny?"):
        if isinstance(event, AgentRunResultEvent):
            result = event

    assert result
    assert result.result
    assert "James Bond" in result.result.output
    assert "secretary" in result.result.output.lower()
