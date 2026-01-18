from perplexity import Perplexity

client = Perplexity()


def perplexity(query: str):
    """Get ranked search results from Perplexity's continuously refreshed index with advanced filtering and customization options."""

    search = client.search.create(query=query)
    return search
