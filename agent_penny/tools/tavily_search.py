from functools import cache
from typing import TypedDict

from tavily import TavilyClient  # type: ignore[import-untyped]


class TavilySearchResult(TypedDict):
    url: str
    title: str
    content: str
    score: float


class TavilySearchResponse(TypedDict):
    query: str
    results: list[TavilySearchResult]
    response_time: float
    request_id: str


@cache
def client():
    return TavilyClient()


def tavily_search(query: str) -> TavilySearchResponse:
    """Execute a search query using Tavily Search."""
    return client().search(query)
