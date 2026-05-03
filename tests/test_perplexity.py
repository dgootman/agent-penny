import os

import pytest
from loguru import logger

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERPLEXITY_API_KEY"), reason="PERPLEXITY_API_KEY not set"
)


def test_perplexity():
    from agent_penny.tools.perplexity import perplexity

    results = perplexity("Who is Miss Moneypenny?")

    logger.debug("Results", results=results.to_dict())
    assert results
