import os

import pytest
from loguru import logger

from agent_penny.tools.tavily_search import tavily_search

pytestmark = pytest.mark.skipif(
    not os.environ.get("TAVILY_API_KEY"), reason="TAVILY_API_KEY not set"
)


def test_tavily():
    query = "Who is Miss Moneypenny?"

    results = tavily_search(query)

    logger.debug("Results", results=results)

    assert results
    assert results["query"] == query
    assert results["results"]
    assert len(results["results"]) > 0
    assert any("secretary" in r["content"].lower() for r in results["results"])
