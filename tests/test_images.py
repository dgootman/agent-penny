import os
import re
import webbrowser
from typing import Any

import pytest
from loguru import logger
from pydantic_ai import Agent, BinaryImage
from pydantic_ai.capabilities import ImageGeneration
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from tests.utils import init_chainlit_context

IMAGE_PROMPT = "Generate an image of a secret agent secretary."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_name",
    [
        "openai:gpt-5.6-sol",
        "openai:gpt-6-luna",
        "openai-codex:gpt-5.6-sol",
        "openai-codex:gpt-6-luna",
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

    async with agent.run_stream(IMAGE_PROMPT) as result:
        output = await result.get_output()
        assert output

        assert "/private/images/" in output
        match = re.search(r"/private/images/[0-9a-f]+.(jpg|png|webp)", output)
        assert match, f"Unexpected file name in output: {output}"
        image_path = match.group(0)

        assert (user_data.path("images") / image_path.split("/")[-1]).exists()


@pytest.mark.asyncio
@pytest.mark.skipif(
    "OMNIROUTE_API_KEY" not in os.environ, reason="OMNIROUTE_API_KEY not set"
)
@pytest.mark.skipif(
    "OMNIROUTE_BASE_URL" not in os.environ, reason="OMNIROUTE_BASE_URL not set"
)
async def test_omniroute_workaround():
    model = OpenAIResponsesModel(
        model_name="gpt-6-luna",
        provider=OpenAIProvider(
            base_url=os.environ["OMNIROUTE_BASE_URL"],
            api_key=os.environ["OMNIROUTE_API_KEY"],
        ),
    )

    async with Agent(model).run_stream(
        IMAGE_PROMPT,
        capabilities=[ImageGeneration(quality="low")],
        output_type=BinaryImage,
    ) as result:
        with pytest.raises(TypeError, match="'NoneType' object is not iterable"):
            await result.get_output()

    from agent_penny import user_data
    from agent_penny.capabilities.images import ImageGenerationCapability

    await init_chainlit_context()

    agent = Agent(
        model=model,
        capabilities=[ImageGenerationCapability()],
    )

    async with agent.run_stream(IMAGE_PROMPT) as result:
        output = await result.get_output()
        assert output

        assert "/private/images/" in output
        match = re.search(r"/private/images/[0-9a-f]+.(jpg|png|webp)", output)
        assert match, f"Unexpected file name in output: {output}"
        image_path = match.group(0)

        assert (user_data.path("images") / image_path.split("/")[-1]).exists()
