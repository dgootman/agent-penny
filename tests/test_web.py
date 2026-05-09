import json

import pytest


@pytest.mark.asyncio
async def test_fetch_raw():
    from agent_penny.capabilities.web import web_fetch

    result = await web_fetch("https://api.github.com/repos/dgootman/agent-penny")

    assert result
    assert result.success
    assert result.status_code == 200

    assert result.content
    data = json.loads(result.content)
    assert "name" in data
    assert data["name"] == "agent-penny"


@pytest.mark.asyncio
async def test_fetch_markdown():
    from agent_penny.capabilities.web import web_fetch

    result = await web_fetch(
        "https://en.wikipedia.org/wiki/Miss_Moneypenny", format="markdown"
    )

    assert result
    assert result.success
    assert result.status_code == 200

    assert result.content
    content = result.content
    assert "secretary" in content.lower()
    assert "Lois Maxwell" in content
    assert "James Bond" in content
