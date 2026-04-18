import hashlib
import os
from base64 import b64decode
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, override

import openai
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


@dataclass
class ImageGenerationCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        toolset = FunctionToolset()

        if "OPENAI_API_KEY" in os.environ:
            toolset.add_function(generate_image_openai)

        return toolset
