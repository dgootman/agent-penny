import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_PLACES_API_KEY"), reason="GOOGLE_PLACES_API_KEY not set"
)


@pytest.mark.asyncio
async def test_place_search():
    from agent_penny.capabilities import google_maps

    capability = google_maps.GoogleMapsCapability()

    result = await capability.place_search("Science World in Vancouver")

    assert result["places"]

    place = result["places"][0]

    assert place["displayName"]["text"] == "Science World"
    assert "Vancouver" in place["formattedAddress"]
    assert place["googleMapsUri"].startswith("https://maps.google.com/")
    assert 49 < place["location"]["latitude"] < 50
    assert -124 < place["location"]["longitude"] < -122
