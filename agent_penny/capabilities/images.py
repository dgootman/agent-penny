import hashlib
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Literal, override

import httpx
from httpx import HTTPStatusError
from loguru import logger
from pydantic_ai import Agent, BinaryImage, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability, ImageGeneration
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

from agent_penny import user_data


def save_image(prompt: str, image: BinaryImage) -> str:
    images_path = user_data.path("images")
    if not images_path.exists():
        images_path.mkdir()

    extension = mimetypes.guess_extension(image.media_type)
    assert extension

    file_name = f"{hashlib.sha1(prompt.encode()).hexdigest()}{extension}"
    (images_path / file_name).write_bytes(image.data)
    return f"/private/images/{file_name}"


async def generate_image(
    ctx: RunContext[Any],
    prompt: str,
    background: Literal["auto", "transparent", "opaque"] = "auto",
    quality: Literal["low", "medium", "high"] = "medium",
    size: Literal["1024x1024", "1024x1536", "1536x1024", "auto"] = "auto",
    output_format: Literal["png", "webp", "jpeg"] = "jpeg",
) -> str:
    """
    Generate a single image from the prompt and return its web path.
    """

    assert ctx.agent

    async with Agent(ctx.agent.model).run_stream(
        prompt,
        capabilities=[
            ImageGeneration(
                background=background,
                quality=quality,
                size=size,
                output_format=output_format,
            )
        ],
        output_type=BinaryImage,
    ) as result:
        output = await result.get_output()
        return save_image(prompt, output)


async def generate_image_ideogram(
    prompt: str,
    negative_prompt: str | None = None,
    rendering_speed: Literal["TURBO", "DEFAULT", "QUALITY"] = "TURBO",
) -> str:
    """
    Generate a single image from the prompt and return its web path.
    Select the 'TURBO' rendering speed unless explicitly instructed otherwise.
    """

    # Generate with Ideogram 3.0 (POST /v1/ideogram-v3/generate)
    request = {
        "prompt": prompt,
        "rendering_speed": rendering_speed,
    }
    if negative_prompt:
        request["negative_prompt"] = negative_prompt

    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            "https://api.ideogram.ai/v1/ideogram-v3/generate",
            headers={"Api-Key": os.environ["IDEOGRAM_API_KEY"]},
            json=request,
        )

        try:
            response.raise_for_status()
        except HTTPStatusError as e:
            raise ModelRetry("Failed to generate image") from e

        logger.debug("Image generated", response=response.json())

        url = response.json()["data"][0]["url"]
        response = await client.get(url)
        try:
            response.raise_for_status()
        except HTTPStatusError as e:
            raise ModelRetry(f"Failed to get image: {url}") from e

        return save_image(
            prompt, BinaryImage(response.content, media_type="image/jpeg")
        )


@dataclass
class ImageGenerationCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self):
        async def _get_toolset(ctx: RunContext[Any]) -> AgentToolset[Any] | None:
            toolset = FunctionToolset()

            if (
                ctx.agent
                and ctx.agent.model
                and (
                    ctx.agent.model.startswith("openai")
                    if isinstance(ctx.agent.model, str)
                    else (
                        ctx.agent.model.provider
                        and ctx.agent.model.provider.name.startswith("openai")
                    )
                )
            ):
                # Native Image Generation only supported by OpenAI and image-specific Google models
                # https://pydantic.dev/docs/ai/tools-toolsets/native-tools/#image-generation-tool
                toolset.add_function(generate_image)

            if "IDEOGRAM_API_KEY" in os.environ:
                toolset.add_function(generate_image_ideogram)

            return toolset

        return _get_toolset
