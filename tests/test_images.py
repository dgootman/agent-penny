import os
import re
import webbrowser
from typing import Any

import pytest
from loguru import logger
from pydantic_ai import Agent

from tests.utils import init_chainlit_context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_name",
    [
        "openai:gpt-5.6-sol",
        "openai-codex:gpt-5.6-sol",
    ],
)
async def test_generate_image(
    model_name: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    if (
        model_name.startswith("openai-codex:")
        and os.environ.get("OPENAI_CODEX_ENABLE") != "true"
    ):
        pytest.skip("OpenAI Codex not enabled")
        return
    elif (
        model_name.startswith("openai:")
        and os.environ.get("TEST_OPENAI_IMAGES") != "true"
    ):
        # OpenAI tests cost $$$, enable only when needed
        pytest.skip("OpenAI image test not enabled")
        return

    from agent_penny import user_data
    from agent_penny.available_models import resolve_model
    from agent_penny.capabilities.images import ImageGenerationCapability

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

    monkeypatch.delenv("IDEOGRAM_API_KEY", raising=False)

    agent = Agent(
        model=resolve_model(model_name),
        capabilities=[ImageGenerationCapability()],
    )

    async with agent.run_stream(
        "Generate an image of a secret agent secretary."
    ) as result:
        output = await result.get_output()
        assert output

        assert "/private/images/" in output
        match = re.search(r"/private/images/[0-9a-f]+.(jpg|png|webp)", output)
        assert match, f"Unexpected file name in output: {output}"
        image_path = match.group(0)

        assert (user_data.path("images") / image_path.split("/")[-1]).exists()
