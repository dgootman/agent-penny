from datetime import date, datetime
from typing import Literal, NotRequired, TypedDict


class Calendar(TypedDict):
    id: str
    name: str
    description: NotRequired[str]


class CalendarEventAttributes(TypedDict):
    name: str
    description: NotRequired[str]
    location: NotRequired[str]
    start_time: datetime | date
    end_time: datetime | date
    calendar_id: Literal["primary"] | str


class CreateCalendarEventRequest(CalendarEventAttributes):
    """
    Request to create a calendar event.

    Start and end times are either full dates (for all-day events) or date, time, and timezone (for non-all-day events).
    """

    pass


class UpdateCalendarEventRequest(CalendarEventAttributes):
    """
    Request to update a calendar event.

    Start and end times are either full dates (for all-day events) or date, time, and timezone (for non-all-day events).
    """

    id: str


class CalendarEvent(CalendarEventAttributes):
    id: str


MailHeaders = TypedDict(
    "MailHeaders",
    {
        "subject": NotRequired[str],
        "from": str,
        "to": NotRequired[str],
    },
)

MailContentType = Literal["text/plain", "text/markdown"]


class MailMessage(MailHeaders):
    id: str
    received: datetime
    content: str
    content_type: MailContentType


class MailMessageSnippet(MailHeaders):
    id: str
    received: datetime
    snippet: str


class Draft(TypedDict):
    id: str
    message: MailMessage


class DraftRequest(TypedDict):
    subject: str
    to: str
    cc: NotRequired[str]
    bcc: NotRequired[str]
    content: str
    content_type: NotRequired[MailContentType]


class CreateDraftRequest(DraftRequest):
    pass


class CreateDraftResponse(TypedDict):
    id: str


class UpdateDraftRequest(DraftRequest):
    pass


class UpdateDraftResponse(TypedDict):
    id: str
