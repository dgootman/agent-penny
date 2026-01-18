import os
from datetime import datetime

import chainlit as cl
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from loguru import logger


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

    def calendar_list(self):
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

        logger.debug("Listed calendars", calendars=calendars)
        return calendars

    def calendar_list_events(
        self,
        start_time: datetime,
        end_time: datetime,
    ):
        logger.debug(
            "Listing calendar events",
            start_time=start_time,
            end_time=end_time,
        )

        calendars = self.calendar_list()
        calendar_ids = [calendar["id"] for calendar in calendars]

        events = [
            event | {"calendar_id": calendar_id}
            for calendar_id in calendar_ids
            for event in self.calendar_service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
            )
            .execute()["items"]
        ]

        return events

    def email_list_messages(self, query: str | None = None, max_results: int = 100):
        logger.debug("Listing mail messages", query=query, max_results=max_results)
        return (
            self.email_service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()["messages"]
        )
