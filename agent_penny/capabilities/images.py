import hashlib
import os
from base64 import b64decode
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, override

import httpx
import openai
from httpx import HTTPStatusError
from loguru import logger
from pydantic_ai import ModelRetry
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

from agent_penny import user_data


@cache
def client() -> openai.AsyncClient:
    return openai.AsyncClient()


def save_image(prompt: str, content: bytes) -> str:
    images_path = user_data.path("images")
    if not images_path.exists():
        images_path.mkdir()

    file_name = f"{hashlib.sha1(prompt.encode()).hexdigest()}.jpg"
    (images_path / file_name).write_bytes(content)
    return f"/private/images/{file_name}"


async def generate_image_openai(
    prompt: str, quality: Literal["low", "medium", "high"] = "low"
):
    """
    Generate a single image from the prompt and return its web path.
    Select the 'low' quality unless explicitly instructed otherwise.
    """
    response = await client().images.generate(
        prompt=prompt,
        model="gpt-image-1-mini",
        quality=quality,
        size="1536x1024",
        n=1,
    )

    assert response.data

    [image] = response.data

    assert image.b64_json
    return save_image(prompt, b64decode(image.b64_json))


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

        return save_image(prompt, response.content)


@dataclass
class ImageGenerationCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        toolset = FunctionToolset()

        if "OPENAI_API_KEY" in os.environ:
            toolset.add_function(generate_image_openai)

        if "IDEOGRAM_API_KEY" in os.environ:
            toolset.add_function(generate_image_ideogram)

        return toolset
