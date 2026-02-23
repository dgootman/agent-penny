from datetime import date, datetime
from typing import Literal, NotRequired, TypedDict


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
    calendar_id: Literal["primary"] | str


MailMessage = TypedDict(
    "MailMessage",
    {
        "id": str,
        "subject": NotRequired[str],
        "from": str,
        "to": NotRequired[str],
        "received": datetime,
        "content": str,
    },
)


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
