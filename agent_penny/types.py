from datetime import date, datetime
from typing import NotRequired, TypedDict


class Calendar(TypedDict):
    id: str
    name: str
    description: NotRequired[str]


class CalendarEvent(TypedDict):
    id: str
    name: str
    description: NotRequired[str]
    location: NotRequired[str]
    start_time: datetime | date
    end_time: datetime | date
    calendar_id: str


MailMessage = TypedDict(
    "MailMessage",
    {
        "id": str,
        "subject": str,
        "from": str,
        "to": str,
        "received": datetime,
        "content": str,
    },
)
