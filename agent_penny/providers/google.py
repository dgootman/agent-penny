import os
from base64 import urlsafe_b64decode
from datetime import date, datetime
from email import message_from_string
from email.header import decode_header
from io import BytesIO
from zoneinfo import ZoneInfo

import chainlit as cl
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from loguru import logger
from markitdown import MarkItDown

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
        self.calendar_service = build("calendar", "v3", credentials=self.credentials)
        self.email_service = build("gmail", "v1", credentials=self.credentials)

        self.tools = [
            self.calendar_list,
            self.calendar_list_events,
            self.email_list_messages,
        ]

    def calendar_list(self) -> list[Calendar]:
        logger.debug("Listing calendars")

        response = self.calendar_service.calendarList().list().execute()
        calendars = response["items"]

        while page_token := response.get("nextPageToken"):
            response = (
                self.calendar_service.calendarList()
                .list(pageToken=page_token)
                .execute()
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

    def calendar_list_events(
        self,
        start_time: datetime,
        end_time: datetime,
        users_iana_timezone: str,
    ) -> list[CalendarEvent]:
        logger.debug(
            "Listing calendar events",
            start_time=start_time,
            end_time=end_time,
            users_iana_timezone=users_iana_timezone,
        )

        tz = ZoneInfo(users_iana_timezone)

        calendars = self.calendar_list()
        calendar_ids = [calendar["id"] for calendar in calendars]

        calendar_events = {
            calendar_id: self.calendar_service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
            )
            .execute()["items"]
            for calendar_id in calendar_ids
        }

        logger.trace("Google calendar events", calendar_events=calendar_events)

        def google_date_adapter(google_date: dict[str, str]) -> datetime | date:
            if "dateTime" in google_date:
                return datetime.fromisoformat(google_date["dateTime"]).astimezone(tz=tz)
            if "date" in google_date:
                return date.fromisoformat(google_date["date"])
            raise ValueError(f"Invalid date: {google_date}")

        def google_event_adapter(event, calendar_id: str) -> CalendarEvent:
            return CalendarEvent(
                name=event["summary"],
                start_time=google_date_adapter(event["start"]),
                end_time=google_date_adapter(event["end"]),
                calendar_id=calendar_id,
            ) | (
                {"description": event["description"]}
                if event.get("description")
                else {}
            )

        events: list[CalendarEvent] = []

        for calendar_id, google_events in calendar_events.items():
            for event in google_events:
                if event.get("recurrence"):
                    response = (
                        self.calendar_service.events()
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
                        events.append(google_event_adapter(instance, calendar_id))

                else:
                    events.append(google_event_adapter(event, calendar_id))

        return sorted(events, key=lambda event: event["start_time"].isoformat())

    def google_message_adapter(self, message) -> MailMessage:
        email = message_from_string(urlsafe_b64decode(message["raw"]).decode())

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

        return (
            MailMessage(
                id=message["id"],
            )
            | {"from": decode(email["from"])}
            | {"to": decode(email["to"])}
            | {"subject": decode(email["subject"])}
            | {"received": datetime.fromtimestamp(int(message["internalDate"]) / 1000)}
            | {"content": get_payload()}
        )

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
        self, query: str | None = None, max_results: int = 100
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
