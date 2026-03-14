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
    """Event start date for all-day events or date and time with timezone"""
    end_time: datetime | date
    """Event end date for all-day events or date and time with timezone"""
    calendar_id: Literal["primary"] | str


class CreateCalendarEventRequest(CalendarEventAttributes):
    pass


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


class MailMessage(MailHeaders):
    id: str
    received: datetime
    content: str


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


class CreateDraftRequest(DraftRequest):
    pass


class CreateDraftResponse(TypedDict):
    id: str


class UpdateDraftRequest(DraftRequest):
    pass


class UpdateDraftResponse(TypedDict):
    id: str
