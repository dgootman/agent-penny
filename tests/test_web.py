import json

import pytest


@pytest.mark.asyncio
async def test_fetch_raw():
    from agent_penny.capabilities.web import web_fetch

    result = await web_fetch("https://api.github.com/repos/dgootman/agent-penny")

    assert result

    data = json.loads(result)
    assert "name" in data
    assert data["name"] == "agent-penny"


@pytest.mark.asyncio
async def test_fetch_markdown():
    from agent_penny.capabilities.web import web_fetch

    result = await web_fetch(
        "https://en.wikipedia.org/wiki/Miss_Moneypenny", format="markdown"
    )

    assert result
    assert "secretary" in result.lower()
    assert "Lois Maxwell" in result
    assert "James Bond" in result
