from functools import cache

from perplexity import Perplexity
from perplexity.types import SearchCreateResponse


@cache
def client():
    return Perplexity()


def perplexity(query: str) -> SearchCreateResponse:
    """Get ranked search results from Perplexity's continuously refreshed index with advanced filtering and customization options."""

    search = client().search.create(query=query)
    return search
