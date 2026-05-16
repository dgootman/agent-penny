from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal, override

import httpx
from fake_useragent import UserAgent
from httpx import HTTPError
from markitdown import MarkItDown, StreamInfo
from pydantic import BaseModel
from pydantic_ai import ModelRetry
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

md = MarkItDown(enable_plugins=False)
user_agent = UserAgent().chrome

toolset = FunctionToolset()


class WebResponse(BaseModel):
    success: bool
    status_code: int
    content: str


class WebError(BaseModel):
    error: str
    message: str


@toolset.tool_plain()
async def web_fetch(
    url: str,
    *,
    format: Literal["raw", "markdown"] = "raw",
    timeout=15.0,
) -> WebResponse | WebError:
    """
    Fetch a URL and return its response body as raw text or converted markdown.

    Args:
        url: url to fetch
        format: raw or convert to markdown
        timeout: timeout in seconds
    """

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Accept-Encoding": "gzip",  # Respect Wikipedia's Robot Policy: https://wikitech.wikimedia.org/wiki/Robot_policy
                },
            )
        except HTTPError as e:
            return WebError(error=type(e).__name__, message=str(e))

        if format == "raw":
            content = response.text
        elif format == "markdown":
            content = md.convert_stream(
                BytesIO(response.content),
                stream_info=StreamInfo(
                    mimetype=response.headers.get("content-type", "text/html")
                ),
            ).markdown
        else:
            raise ModelRetry(f"Invalid format: {format}")

        return WebResponse(
            success=response.is_success,
            status_code=response.status_code,
            content=content,
        )


@dataclass
class WebFetchCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return toolset
