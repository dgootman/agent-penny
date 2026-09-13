from datetime import datetime


def get_tz_name(dt: datetime) -> str | None:
    """Return the timezone name for a datetime, or ``None`` if it is naive.

    Prefers IANA timezone identifiers exposed by ``zoneinfo`` or ``pytz`` and
    falls back to the timezone display name for fixed-offset timezones.
    """

    if not dt or not dt.tzinfo:
        return None

    # 1. Check for standard zoneinfo (.key)
    if hasattr(dt.tzinfo, "key"):
        assert isinstance(dt.tzinfo.key, str)
        return dt.tzinfo.key

    # 2. Check for legacy pytz (.zone)
    if hasattr(dt.tzinfo, "zone"):
        assert isinstance(dt.tzinfo.zone, str)
        return dt.tzinfo.zone

    # 3. Fallback for Pydantic TzInfo or standard fixed-offset zones
    return dt.tzinfo.tzname(dt)
