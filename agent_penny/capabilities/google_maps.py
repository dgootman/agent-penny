import os
from dataclasses import dataclass
from typing import Any, Literal, override

import httpx
from pydantic_ai import AgentToolset, FunctionToolset, Tool
from pydantic_ai.capabilities import AbstractCapability

# https://developers.google.com/maps/documentation/places/web-service/text-search#required-parameters
AdditionalField = Literal[
    "places.allowsDogs",
    "places.curbsidePickup",
    "places.delivery",
    "places.dineIn",
    "places.editorialSummary",
    "places.evChargeAmenitySummary",
    "places.evChargeOptions",
    "places.fuelOptions",
    "places.generativeSummary",
    "places.goodForChildren",
    "places.goodForGroups",
    "places.goodForWatchingSports",
    "places.liveMusic",
    "places.menuForChildren",
    "places.neighborhoodSummary",
    "places.parkingOptions",
    "places.paymentOptions",
    "places.outdoorSeating",
    "places.reservable",
    "places.restroom",
    "places.reviews",
    "places.reviewSummary",
    "places.servesBeer",
    "places.servesBreakfast",
    "places.servesBrunch",
    "places.servesCocktails",
    "places.servesCoffee",
    "places.servesDessert",
    "places.servesDinner",
    "places.servesLunch",
    "places.servesVegetarianFood",
    "places.servesWine",
    "places.takeout",
]


@dataclass()
class GoogleMapsCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        if "GOOGLE_PLACES_API_KEY" not in os.environ:
            return None

        return FunctionToolset(
            [
                Tool(self.place_search),
            ]
        )

    async def place_search(
        self,
        query: str,
        *,
        additional_fields: list[AdditionalField] | None = None,
    ) -> dict:
        """Returns information about a set of places based on a string (for example, "pizza in New York" or "shoe stores near Ottawa" or "123 Main Street"). The service responds with a list of places matching the text string and any location bias that has been set."""

        async with httpx.AsyncClient(
            timeout=10, headers={"X-Goog-Api-Key": os.environ["GOOGLE_PLACES_API_KEY"]}
        ) as client:
            # https://developers.google.com/maps/documentation/places/web-service/text-search
            response = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    # https://developers.google.com/maps/documentation/places/web-service/text-search#required-parameters
                    "X-Goog-FieldMask": ",".join(
                        [
                            ## The following fields trigger the Text Search Essentials ID Only SKU:
                            # "places.attributions",
                            # "places.id",
                            # "places.name*",
                            # "nextPageToken",
                            # "places.movedPlace",
                            # "places.movedPlaceId",
                            ## The following fields trigger the Text Search Pro SKU:
                            # "places.accessibilityOptions",
                            # "places.addressComponents",
                            # "places.addressDescriptor*",
                            # "places.adrFormatAddress",
                            # "places.businessStatus",
                            # "places.containingPlaces",
                            "places.displayName",
                            "places.formattedAddress",
                            # "places.googleMapsLinks",
                            "places.googleMapsUri",
                            # "places.iconBackgroundColor",
                            # "places.iconMaskBaseUri",
                            "places.location",
                            # "places.openingDate",
                            # "places.photos",
                            # "places.plusCode",
                            # "places.postalAddress",
                            # "places.primaryType",
                            # "places.primaryTypeDisplayName",
                            # "places.pureServiceAreaBusiness",
                            # "places.shortFormattedAddress",
                            # "places.searchUri",
                            # "places.subDestinations",
                            # "places.timeZone",
                            # "places.types",
                            # "places.utcOffsetMinutes",
                            # "places.viewport",
                            ## The following fields trigger the Text Search Enterprise SKU:
                            "places.currentOpeningHours",
                            "places.currentSecondaryOpeningHours",
                            # "places.internationalPhoneNumber",
                            # "places.nationalPhoneNumber",
                            "places.priceLevel",
                            # "places.priceRange",
                            "places.rating",
                            # "places.regularOpeningHours",
                            # "places.regularSecondaryOpeningHours",
                            # "places.transitStation",
                            "places.userRatingCount",
                            "places.websiteUri",
                        ]
                        + list[str](additional_fields or [])
                    )
                },
                json={"textQuery": query},
            )
            response.raise_for_status()
            return response.json()
