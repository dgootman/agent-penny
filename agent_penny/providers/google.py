from __future__ import annotations

import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, time, tzinfo
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage
from io import BytesIO
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

import chainlit as cl
from bidict import bidict
from dateutil.rrule import (
    DAILY,
    FR,
    HOURLY,
    MO,
    MONTHLY,
    SA,
    SU,
    TH,
    TU,
    WE,
    WEEKLY,
    YEARLY,
    rrule,
    weekday,
)
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger
from markdown import markdown
from markitdown import MarkItDown, StreamInfo
from pydantic_ai import FunctionToolset, ModelRetry

from agent_penny.chainlit_utils import get_user
from agent_penny.date_utils import get_tz_name
from agent_penny.tools.approval import ApprovalRequiredToolset
from agent_penny.types import (
    Calendar,
    CalendarEvent,
    CalendarEventAttributes,
    CalendarEventId,
    CalendarEventRecurrence,
    CreateCalendarEventRequest,
    CreateDraftRequest,
    CreateDraftResponse,
    Draft,
    DraftRequest,
    Frequency,
    MailContentType,
    MailMessage,
    MailMessageSnippet,
    UpdateCalendarEventRequest,
    UpdateDraftRequest,
    UpdateDraftResponse,
    Weekday,
)

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3 import CalendarResource, Event, EventDateTime
    from googleapiclient._apis.gmail.v1 import GmailResource

md = MarkItDown(enable_plugins=False)

RruleFrequency = Literal[0, 1, 2, 3, 4, 5, 6]

freq_to_rrule: bidict[Frequency, RruleFrequency] = bidict(
    {
        "yearly": YEARLY,
        "monthly": MONTHLY,
        "weekly": WEEKLY,
        "daily": DAILY,
        "hourly": HOURLY,
    }  # type: ignore[arg-type]
)

weekday_to_rrule: bidict[Weekday, weekday] = bidict(
    {
        "Monday": MO,
        "Tuesday": TU,
        "Wednesday": WE,
        "Thursday": TH,
        "Friday": FR,
        "Saturday": SA,
        "Sunday": SU,
    }  # type: ignore[arg-type]
)


class GoogleProvider:
    def __init__(self, user: cl.User | None = None):
        user = user or get_user()

        token = user.metadata["token"]
        refresh_token = user.metadata["refresh_token"]

        self.credentials = Credentials(
            token,
            refresh_token=refresh_token,
            client_id=os.environ["OAUTH_GOOGLE_CLIENT_ID"],
            client_secret=os.environ["OAUTH_GOOGLE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
        )

        self.toolset = ApprovalRequiredToolset(
            FunctionToolset(
                [
                    self.calendar_create_event,
                    self.calendar_update_event,
                    self.calendar_delete_event,
                    self.calendar_list,
                    self.calendar_list_events,
                    self.email_list_messages,
                    self.email_get_message,
                    self.email_list_drafts,
                    self.email_get_draft,
                    self.email_create_draft,
                    self.email_update_draft,
                    self.email_delete_draft,
                ]  # type: ignore[ty:invalid-argument-type]
            ),
            approval_required_func=lambda ctx, tool_def, tool_args: (
                tool_def.name
                in [
                    "calendar_create_event",
                    "calendar_update_event",
                    "calendar_delete_event",
                ]
            ),
        )

    def calendar_service(self) -> CalendarResource:
        return build("calendar", "v3", credentials=self.credentials)

    def email_service(self) -> GmailResource:
        return build("gmail", "v1", credentials=self.credentials)

    def calendar_list(self) -> list[Calendar]:
        logger.debug("Listing calendars")

        with self.calendar_service() as calendar_service:
            response = calendar_service.calendarList().list().execute()
            google_calendars = response["items"]

            while page_token := response.get("nextPageToken"):
                response = (
                    calendar_service.calendarList().list(pageToken=page_token).execute()
                )
                google_calendars += response["items"]

        logger.trace("Google calendars", google_calendars=google_calendars)

        def adapt(google_calendar) -> Calendar:
            calendar: Calendar = {
                "id": google_calendar["id"],
                "name": google_calendar.get("summaryOverride")
                or google_calendar["summary"],
            }

            if description := calendar.get("description"):
                calendar["description"] = description

            return calendar

        calendars = [adapt(calendar) for calendar in google_calendars]

        logger.debug("Listed calendars", calendars=calendars)

        return calendars

    def _google_event_adapter(
        self, event: Event, calendar_id: str, tz: tzinfo | None
    ) -> CalendarEvent:
        def date_adapter(google_date: EventDateTime) -> datetime:
            if tz is None:
                raise ValueError("Missing timezone")
            if "dateTime" in google_date:
                return datetime.fromisoformat(google_date["dateTime"]).astimezone(tz=tz)
            if "date" in google_date:
                return datetime.fromisoformat(google_date["date"]).astimezone(tz=tz)
            raise ValueError(f"Invalid date: {google_date}")

        calendar_event: CalendarEvent = {
            "id": event["id"],
            "name": event["summary"],
            "start_time": date_adapter(event["start"]),
            "end_time": date_adapter(event["end"]),
            "calendar_id": calendar_id,
        }

        for optional_field in ["description", "location"]:
            if event.get(optional_field):
                calendar_event[optional_field] = event[optional_field]  # type: ignore[literal-required,ty:invalid-key]

        return calendar_event

    def calendar_list_events(
        self,
        start_time: datetime,
        end_time: datetime,
        users_iana_timezone: str,
        calendar_ids: list[str] | None = None,
    ) -> list[CalendarEvent]:
        logger.debug(
            "Listing calendar events",
            start_time=start_time,
            end_time=end_time,
            users_iana_timezone=users_iana_timezone,
            calendar_ids=calendar_ids,
        )

        tz = ZoneInfo(users_iana_timezone)

        if start_time.tzinfo is None and end_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=tz)
            end_time = end_time.replace(tzinfo=tz)
        elif start_time.tzinfo is None:
            raise ValueError("Start time is missing a timezone")
        elif end_time.tzinfo is None:
            raise ValueError("End time is missing a timezone")

        if not calendar_ids:
            calendars = self.calendar_list()
            calendar_ids = [calendar["id"] for calendar in calendars]

        with self.calendar_service() as calendar_service:
            calendar_events = {}
            for calendar_id in calendar_ids:
                try:
                    calendar_events[calendar_id] = (
                        calendar_service.events()
                        .list(
                            calendarId=calendar_id,
                            timeMin=start_time.isoformat(),
                            timeMax=end_time.isoformat(),
                            singleEvents=True,
                            showDeleted=False,
                        )
                        .execute()["items"]
                    )
                except HttpError as e:
                    if e.status_code == 404:
                        raise ModelRetry(f"Calendar not found: {calendar_id}")
                    raise e

            logger.trace("Google calendar events", calendar_events=calendar_events)

            events = [
                self._google_event_adapter(event, calendar_id, tz)
                for calendar_id, google_events in calendar_events.items()
                for event in google_events
            ]

        return sorted(events, key=lambda event: event["start_time"].isoformat())

    def _calendar_request_adapter(self, request: CalendarEventAttributes) -> Event:
        def tz_decorator(dt: EventDateTime, value: datetime):
            tz = get_tz_name(value)
            assert tz
            dt["timeZone"] = tz
            return dt

        def datetime_adapter(value: datetime) -> EventDateTime:
            return tz_decorator({"dateTime": value.isoformat()}, value)

        def date_adapter(value: datetime) -> EventDateTime:
            return tz_decorator({"date": value.date().isoformat()}, value)

        def recurrence_adapter(recurrence: CalendarEventRecurrence) -> str:
            rule = rrule(
                freq=freq_to_rrule[recurrence["frequency"]],
                interval=recurrence.get("interval", 1),
                byweekday=[weekday_to_rrule[d] for d in recurrence["weekdays"]]
                if "weekdays" in recurrence
                else None,
            )

            # As per https://developers.google.com/workspace/calendar/api/v3/reference/events/insert:
            # DTSTART and DTEND lines are not allowed in this field; event start and end times are specified in the start and end fields.
            rule._dtstart = None  # type: ignore[attr-defined, ty:unresolved-attribute]

            return str(rule)

        start, end = map(
            date_adapter
            if all(
                t.time() == time.min
                for t in [request["start_time"], request["end_time"]]
            )
            else datetime_adapter,
            [request["start_time"], request["end_time"]],
        )

        event: Event = {
            "summary": request["name"],
            "start": start,
            "end": end,
        }

        if request.get("location"):
            event["location"] = request["location"]

        if request.get("description"):
            event["description"] = request["description"]

        if request.get("recurrence"):
            event["recurrence"] = [recurrence_adapter(r) for r in request["recurrence"]]

        return event

    def calendar_create_event(
        self, request: CreateCalendarEventRequest
    ) -> CalendarEvent:
        logger.debug("Adding calendar event", request=request)

        if request["start_time"].tzinfo is None:
            raise ModelRetry("Start time is missing a timezone")
        elif request["end_time"].tzinfo is None:
            raise ModelRetry("End time is missing a timezone")

        tz = request["start_time"].tzinfo

        google_request = self._calendar_request_adapter(request)

        logger.trace("Inserting Google calendar event", google_request=google_request)

        with self.calendar_service() as calendar_service:
            google_event = (
                calendar_service.events()
                .insert(calendarId=request["calendar_id"], body=google_request)
                .execute()
            )

        logger.trace("Inserted Google calendar event", google_event=google_event)

        event = self._google_event_adapter(google_event, request["calendar_id"], tz)

        logger.info("Added calendar event", event=event)

        return event

    def calendar_update_event(
        self, request: UpdateCalendarEventRequest
    ) -> CalendarEvent:
        logger.debug("Updating calendar event", request=request)

        tz = (
            request["start_time"].tzinfo
            if isinstance(request["start_time"], datetime)
            else None
        )

        google_request = self._calendar_request_adapter(request)

        logger.trace("Updating Google calendar event", google_request=google_request)

        with self.calendar_service() as calendar_service:
            google_event = (
                calendar_service.events()
                .update(
                    calendarId=request["calendar_id"],
                    eventId=request["id"],
                    body=google_request,
                )
                .execute()
            )

        logger.trace("Updated Google calendar event", google_event=google_event)

        event = self._google_event_adapter(google_event, request["calendar_id"], tz)

        logger.info("Updated calendar event", event=event)

        return event

    def calendar_delete_event(self, event: CalendarEventId) -> None:
        logger.debug("Deleting calendar event", event=event)

        with self.calendar_service() as calendar_service:
            google_event = (
                calendar_service.events()
                .get(calendarId=event["calendar_id"], eventId=event["id"])
                .execute()
            )

            # Log this as debug rather than trace to keep a record of events
            # that may have been deleted accidentally
            logger.debug("Deleting Google calendar event", google_event=google_event)

            calendar_service.events().delete(
                calendarId=event["calendar_id"], eventId=event["id"]
            ).execute()

        logger.info("Deleted calendar event", event=event)

    def google_message_adapter(self, message) -> MailMessage:
        email = message_from_bytes(urlsafe_b64decode(message["raw"]))

        def get_payload() -> tuple[MailContentType, str]:
            payloads = list(email.walk())

            text_part = next(
                (p for p in payloads if p.get_content_type() == "text/plain"),
                None,
            )
            if text_part:
                cte = text_part.get("content-transfer-encoding")
                if cte in ["quoted-printable", "base64"]:
                    decoded_bytes = text_part.get_payload(decode=True)

                    # TODO: Replace fallback with charset inference based on charset in payload
                    try:
                        return "text/plain", decoded_bytes.decode()  # type: ignore[union-attr,ty:unresolved-attribute]
                    except UnicodeDecodeError:
                        return "text/plain", decoded_bytes.decode("latin-1")  # type: ignore[union-attr,ty:unresolved-attribute]

                payload = text_part.get_payload()
                if isinstance(payload, str):
                    return "text/plain", payload
                return "text/plain", text_part.get_payload(decode=True).decode()  # type: ignore[union-attr,ty:unresolved-attribute]

            html_part = next(
                (p for p in payloads if p.get_content_type() == "text/html"),
                None,
            )
            if html_part:
                return "text/markdown", md.convert_stream(
                    BytesIO(html_part.get_payload(decode=True)),  # type: ignore[arg-type,ty:invalid-argument-type]
                    stream_info=StreamInfo(
                        mimetype=html_part.get_content_type(),
                        charset=html_part.get_content_charset(),
                    ),
                ).markdown

            raise ValueError(
                f"Unsupported content types: {', '.join(p.get_content_type() for p in payloads)}"
            )

        def decode(value):
            return "".join(
                content.decode(charset or "utf-8")
                if isinstance(content, bytes)
                else content
                for content, charset in decode_header(value)
            )

        content_type, payload = get_payload()

        mail_message: MailMessage = {
            "id": message["id"],
            "from": decode(email["from"]),
            "received": datetime.fromtimestamp(int(message["internalDate"]) / 1000),
            "content": payload,
            "content_type": content_type,
        }

        if email["subject"]:
            mail_message["subject"] = decode(email["subject"])

        if email["to"]:
            mail_message["to"] = decode(email["to"])

        return mail_message

    def email_get_message(self, id: str) -> MailMessage:
        logger.trace("Getting message", message_id=id)

        with self.email_service() as email_service:
            message = (
                email_service.users()
                .messages()
                .get(userId="me", id=id, format="raw")
                .execute()
            )

        logger.trace("Google message", message_id=id, message=message)

        return self.google_message_adapter(message)

    def email_list_messages(
        self, query="in:inbox", max_results=10
    ) -> list[MailMessageSnippet]:
        logger.debug("Listing mail messages", query=query, max_results=max_results)

        with self.email_service() as email_service:
            response = (
                email_service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            logger.trace("Google messages response", response=response)

            if response["resultSizeEstimate"] == 0:
                logger.debug("No messages listed")

                assert "messages" not in response or len(response["messages"]) == 0
                return []

            messages_metadata = response["messages"]

            logger.debug(f"Listed {len(messages_metadata)} mail messages")

            logger.trace(
                "Google messages metadata", messages_metadata=messages_metadata
            )

            messages: list[MailMessageSnippet] = []

            for message_metadata in messages_metadata:
                message = (
                    email_service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_metadata["id"],
                        format="metadata",
                        metadataHeaders=["subject", "from", "to"],
                    )
                    .execute()
                )

                logger.trace(
                    "Google message", message_id=message_metadata["id"], message=message
                )

                def get_header(name: str) -> str | None:
                    for header in message["payload"]["headers"]:
                        if header["name"].lower() == name:
                            return header["value"]
                    return None

                def get_required_header(name: str) -> str:
                    result = get_header(name)
                    if result is None:
                        raise ValueError(f"Message is missing {name} header: {message}")
                    return result

                message_snippet: MailMessageSnippet = {
                    "id": message["id"],
                    "subject": get_required_header("subject"),
                    "from": get_required_header("from"),
                    "received": datetime.fromtimestamp(
                        int(message["internalDate"]) / 1000
                    ),
                    "snippet": message["snippet"],
                }

                if to := get_header("to"):
                    message_snippet["to"] = to

                messages.append(message_snippet)

            return messages

    def email_list_drafts(self) -> list[Draft]:
        logger.debug("List mail drafts")

        with self.email_service() as email_service:
            draft_metadata = email_service.users().drafts().list(userId="me").execute()

        logger.trace("Google drafts listed", draft_metadata=draft_metadata)

        return [self.email_get_draft(draft["id"]) for draft in draft_metadata["drafts"]]

    def email_get_draft(self, id: str) -> Draft:
        logger.debug("Get mail draft", id=id)

        with self.email_service() as email_service:
            draft = (
                email_service.users()
                .drafts()
                .get(userId="me", id=id, format="raw")
                .execute()
            )

        logger.trace("Google draft retrieved", draft=draft)

        return {
            "id": draft["id"],
            "message": self.google_message_adapter(draft["message"]),
        }

    def draft_to_encoded_message(self, draft: DraftRequest) -> str:
        email = EmailMessage()

        content = draft["content"]
        subtype = draft.get("content_type", "text/plain").split("/")[-1]

        if subtype == "markdown":
            # Convert to HTML
            content = markdown(content)
            subtype = "html"

        email["Subject"] = draft["subject"]
        email["To"] = draft["to"]
        if draft.get("cc"):
            email["Cc"] = draft["cc"]
        if draft.get("bcc"):
            email["Bcc"] = draft["bcc"]
        email.set_content(content, subtype=subtype)

        encoded_message = urlsafe_b64encode(email.as_bytes()).decode()

        return encoded_message

    def email_create_draft(self, request: CreateDraftRequest) -> CreateDraftResponse:
        logger.debug("Creating mail draft", request=request)

        encoded_message = self.draft_to_encoded_message(request)

        with self.email_service() as email_service:
            draft = (
                email_service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": encoded_message}})
                .execute()
            )

        logger.trace("Google draft created", draft=draft)

        return {"id": draft["id"]}

    def email_update_draft(
        self, id: str, request: UpdateDraftRequest
    ) -> UpdateDraftResponse:
        logger.debug("Update mail draft", id=id, request=request)

        # encoded message
        encoded_message = self.draft_to_encoded_message(request)

        with self.email_service() as email_service:
            draft = (
                email_service.users()
                .drafts()
                .update(userId="me", id=id, body={"message": {"raw": encoded_message}})
                .execute()
            )

        logger.trace("Google draft updated", draft=draft)

        return {"id": draft["id"]}

    def email_delete_draft(self, id: str) -> None:
        logger.debug("Delete mail draft", id=id)

        with self.email_service() as email_service:
            email_service.users().drafts().delete(userId="me", id=id).execute()

        logger.trace("Google draft deleted", id=id)
