import os
from base64 import urlsafe_b64decode
from datetime import date, datetime, tzinfo
from email import message_from_bytes
from email.header import decode_header
from io import BytesIO
from zoneinfo import ZoneInfo

import chainlit as cl
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger
from markitdown import MarkItDown
from pydantic_ai import ModelRetry

from ..types import Calendar, CalendarEvent, MailMessage

md = MarkItDown(enable_plugins=False)


class GoogleProvider:
    def __init__(self, user: cl.User):
        token = user.metadata["token"]
        refresh_token = user.metadata["refresh_token"]

        self.credentials = Credentials(
            token,
            refresh_token=refresh_token,
            client_id=os.environ["OAUTH_GOOGLE_CLIENT_ID"],
            client_secret=os.environ["OAUTH_GOOGLE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
        )

        # The Calendar API keeps throwing `SSLError: [SSL] record layer failure (_ssl.c:2580)` if the instance is reused.
        # Instead, we'll use a context-managed instance whenever interacting with the Calendar API
        # self.calendar_service = build("calendar", "v3", credentials=self.credentials)

        self.email_service = build("gmail", "v1", credentials=self.credentials)

        self.tools = [
            self.calendar_add_event,
            self.calendar_list,
            self.calendar_list_events,
            self.email_list_messages,
        ]

    def calendar_service(self):
        return build("calendar", "v3", credentials=self.credentials)

    def calendar_list(self) -> list[Calendar]:
        logger.debug("Listing calendars")

        with self.calendar_service() as calendar_service:
            response = calendar_service.calendarList().list().execute()
            calendars = response["items"]

            while page_token := response.get("nextPageToken"):
                response = (
                    calendar_service.calendarList().list(pageToken=page_token).execute()
                )
                calendars += response["items"]

        logger.trace("Google calendars", calendars=calendars)

        calendars = [
            Calendar(
                id=calendar["id"],
                name=calendar.get("summaryOverride") or calendar["summary"],
            )
            | (
                {"description": calendar["description"]}
                if calendar.get("description")
                else {}
            )
            for calendar in calendars
        ]

        logger.debug("Listed calendars", calendars=calendars)

        return calendars

    def google_event_adapter(
        self, event, calendar_id: str, tz: tzinfo | None
    ) -> CalendarEvent:
        def date_adapter(google_date: dict[str, str]) -> datetime | date:
            if "dateTime" in google_date:
                if tz is None:
                    raise ValueError("Missing timezone")
                return datetime.fromisoformat(google_date["dateTime"]).astimezone(tz=tz)
            if "date" in google_date:
                return date.fromisoformat(google_date["date"])
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
                calendar_event[optional_field] = event[optional_field]  # type: ignore[literal-required]

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
                        )
                        .execute()["items"]
                    )
                except HttpError as e:
                    if e.status_code == 404:
                        raise ModelRetry(f"Calendar not found: {calendar_id}")
                    raise e

            logger.trace("Google calendar events", calendar_events=calendar_events)

            events: list[CalendarEvent] = []

            for calendar_id, google_events in calendar_events.items():
                for event in google_events:
                    if event.get("recurrence"):
                        response = (
                            calendar_service.events()
                            .instances(
                                calendarId=calendar_id,
                                eventId=event["id"],
                                timeMin=start_time.isoformat(),
                                timeMax=end_time.isoformat(),
                            )
                            .execute()
                        )

                        logger.trace(
                            "Google calendar events for recurring event",
                            eventId=event["id"],
                            response=response,
                        )

                        for instance in response["items"]:
                            events.append(
                                self.google_event_adapter(instance, calendar_id, tz)
                            )

                    else:
                        events.append(self.google_event_adapter(event, calendar_id, tz))

        return sorted(events, key=lambda event: event["start_time"].isoformat())

    def calendar_add_event(self, event: CalendarEvent) -> CalendarEvent:
        logger.debug("Adding calendar event", event=event)

        tz = (
            event["start_time"].tzinfo
            if isinstance(event["start_time"], datetime)
            else None
        )

        def date_adapter(value: date | datetime) -> dict[str, str]:
            if isinstance(value, datetime):
                return {"dateTime": value.isoformat()}
            if isinstance(value, date):
                return {"date": value.isoformat()}
            raise ValueError(f"Invalid date: {value}")

        google_event = {
            "summary": event["name"],
            "location": event.get("location"),
            "description": event.get("description"),
            "start": date_adapter(event["start_time"]),
            "end": date_adapter(event["end_time"]),
        }

        logger.trace("Inserting Google calendar event", google_event=google_event)

        with self.calendar_service() as calendar_service:
            google_event = (
                calendar_service.events()
                .insert(calendarId=event["calendar_id"], body=google_event)
                .execute()
            )

        logger.trace("Inserted Google calendar event", google_event=google_event)

        event = self.google_event_adapter(google_event, event["calendar_id"], tz)

        logger.info("Added calendar event", event=event)

        return event

    def google_message_adapter(self, message) -> MailMessage:
        email = message_from_bytes(urlsafe_b64decode(message["raw"]))

        def get_payload():
            payloads = list(email.walk())

            text_part = next(
                (p for p in payloads if p.get_content_type() == "text/plain"),
                None,
            )
            if text_part:
                cte = text_part.get("content-transfer-encoding")
                if cte in ["quoted-printable", "base64"]:
                    return text_part.get_payload(decode=True).decode()
                payload = text_part.get_payload()
                if isinstance(payload, str):
                    return payload
                return text_part.get_payload(decode=True).decode()

            html_part = next(
                (p for p in payloads if p.get_content_type() == "text/html"),
                None,
            )
            if html_part:
                return md.convert_stream(
                    BytesIO(html_part.get_payload(decode=True))
                ).text_content

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

        mail_message: MailMessage = {
            "id": message["id"],
            "from": decode(email["from"]),
            "subject": decode(email["subject"]),
            "received": datetime.fromtimestamp(int(message["internalDate"]) / 1000),
            "content": get_payload(),
        }

        if email["to"]:
            mail_message["to"] = decode(email["to"])

        return mail_message

    def email_get_message(self, id: str) -> MailMessage:
        message = (
            self.email_service.users()
            .messages()
            .get(userId="me", id=id, format="raw")
            .execute()
        )

        logger.trace("Google message", message_id=id, message=message)

        return self.google_message_adapter(message)

    def email_list_messages(
        self, query="in:inbox", max_results=100
    ) -> list[MailMessage]:
        logger.debug("Listing mail messages", query=query, max_results=max_results)

        message_metadata = (
            self.email_service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()["messages"]
        )

        logger.debug(f"Listed {len(message_metadata)} mail messages")

        logger.trace("Google messages metadata", message_metadata=message_metadata)

        return [self.email_get_message(message["id"]) for message in message_metadata]
