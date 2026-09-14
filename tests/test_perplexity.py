import os

import pytest
from loguru import logger

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERPLEXITY_API_KEY"), reason="PERPLEXITY_API_KEY not set"
)


@pytest.mark.asyncio
async def test_perplexity():
    from agent_penny.capabilities.perplexity import PerplexityCapability

    capability = PerplexityCapability(os.environ["PERPLEXITY_API_KEY"])

    results = await capability.perplexity("Who is Miss Moneypenny?")

    logger.debug("Results", results=results.to_dict())
    assert results
