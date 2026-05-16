import json

import pytest


@pytest.mark.asyncio
async def test_fetch_raw():
    from agent_penny.capabilities.web import WebResponse, web_fetch

    result = await web_fetch("https://api.github.com/repos/dgootman/agent-penny")

    assert result
    assert isinstance(result, WebResponse)
    assert result.success
    assert result.status_code == 200

    assert result.content
    data = json.loads(result.content)
    assert "name" in data
    assert data["name"] == "agent-penny"


@pytest.mark.asyncio
async def test_fetch_markdown():
    from agent_penny.capabilities.web import WebResponse, web_fetch

    result = await web_fetch(
        "https://en.wikipedia.org/wiki/Miss_Moneypenny", format="markdown"
    )

    assert result
    assert isinstance(result, WebResponse)
    assert result.success
    assert result.status_code == 200

    assert result.content
    content = result.content
    assert "secretary" in content.lower()
    assert "Lois Maxwell" in content
    assert "James Bond" in content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,timeout,errors",
    [
        (
            "https://tools-httpstatus.pickup-services.com/200?sleep=1000",
            0.1,
            ["TimeoutError"],
        ),
        ("https://no-such.example.org", 5, ["ClientConnectorDNSError"]),
    ],
)
async def test_fetch_error(url: str, timeout: float, errors: list[str]):
    from agent_penny.capabilities.web import WebError, web_fetch

    result = await web_fetch(url, timeout=timeout)

    assert result
    assert isinstance(result, WebError)
    assert result.error in errors
