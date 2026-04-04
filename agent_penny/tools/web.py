from typing import Literal

import requests
from fake_useragent import UserAgent
from markitdown import MarkItDown
from pydantic_ai import ModelRetry

md = MarkItDown(enable_plugins=False)
ua = UserAgent()


def web_fetch(url: str, *, format: Literal["raw", "markdown"] = "raw"):
    """Fetch a URL and return its response body as raw text or converted markdown."""
    response = requests.get(url, headers={"user-agent": ua.chrome})
    if not response.ok:
        raise ModelRetry(
            f"Fetching failed: HTTP {response.status_code}\n{response.text}"
        )

    if format == "raw":
        return response.text
    elif format == "markdown":
        return md.convert_response(response).markdown
    else:
        raise ModelRetry(f"Invalid format: {format}")
