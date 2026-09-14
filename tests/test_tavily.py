import os

import pytest
from loguru import logger
from pydantic import TypeAdapter

pytestmark = pytest.mark.skipif(
    not os.environ.get("TAVILY_API_KEY"), reason="TAVILY_API_KEY not set"
)


@pytest.mark.asyncio
async def test_tavily():
    from agent_penny.capabilities.tavily import TavilyCapability, TavilySearchResponse

    capability = TavilyCapability(os.environ["TAVILY_API_KEY"])

    query = "Who is Miss Moneypenny?"

    results = await capability.tavily_search(query)

    logger.debug("Results", results=results)

    assert results
    TypeAdapter(TavilySearchResponse).validate_python(results)
    assert results["query"] == query
    assert results["results"]
    assert len(results["results"]) > 0
    assert any("secretary" in r["content"].lower() for r in results["results"])
