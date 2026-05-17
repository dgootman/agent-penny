from asyncio import TimeoutError
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal, override

import aiohttp
from aiohttp import ClientConnectorDNSError, ClientError
from fake_useragent import UserAgent
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
    error: Literal["Timeout", "DnsLookup"] | str
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

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout), headers={"User-Agent": user_agent}
    ) as session:
        try:
            async with session.get(url) as response:
                if format == "raw":
                    content = await response.text()
                elif format == "markdown":
                    content = md.convert_stream(
                        BytesIO(await response.content.read()),
                        stream_info=StreamInfo(
                            mimetype=response.content_type or "text/html"
                        ),
                    ).markdown
                else:
                    raise ModelRetry(f"Invalid format: {format}")

                return WebResponse(
                    success=response.ok,
                    status_code=response.status,
                    content=content,
                )
        except (ClientError, TimeoutError) as e:
            error_type_map: dict[type[Exception], str] = {
                TimeoutError: "TimeoutError",
                ClientConnectorDNSError: "DnsLookupError",
            }

            error = error_type_map.get(type(e)) or type(e).__name__
            return WebError(error=error, message=str(e))


@dataclass
class WebFetchCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return toolset
