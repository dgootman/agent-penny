from datetime import datetime
from typing import Literal, NotRequired, TypedDict

Frequency = Literal["yearly", "monthly", "weekly", "daily", "hourly"]

Weekday = Literal[
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]


class Calendar(TypedDict):
    id: str
    name: str
    description: NotRequired[str]


class CalendarEventId(TypedDict):
    id: str
    calendar_id: Literal["primary"] | str


class CalendarEventRecurrence(TypedDict):
    frequency: Frequency
    interval: NotRequired[int]
    weekdays: NotRequired[list[Weekday]]


class CalendarEventAttributes(TypedDict):
    name: str
    description: NotRequired[str]
    location: NotRequired[str]
    start_time: datetime
    end_time: datetime
    recurrence: NotRequired[list[CalendarEventRecurrence]]


class CreateCalendarEventRequest(CalendarEventAttributes):
    """
    Request to create a calendar event.

    Start and end times must specify a timezone.
    """

    calendar_id: Literal["primary"] | str


class UpdateCalendarEventRequest(CalendarEventId, CalendarEventAttributes):
    """
    Request to update a calendar event.

    Start and end times must specify a timezone.
    """


class CalendarEvent(CalendarEventId, CalendarEventAttributes):
    """
    Calendar Event information.
    """


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
