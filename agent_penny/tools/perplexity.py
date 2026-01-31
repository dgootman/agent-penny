from perplexity import Perplexity

_client: Perplexity | None = None


def perplexity(query: str):
    """Get ranked search results from Perplexity's continuously refreshed index with advanced filtering and customization options."""

    global _client

    if not _client:
        _client = Perplexity()

    search = _client.search.create(query=query)
    return search
