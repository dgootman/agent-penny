import getpass
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import chainlit as cl
import pytest
from dateutil.relativedelta import relativedelta
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from loguru import logger
from pydantic import TypeAdapter

from agent_penny.auth.google import ExtendedGoogleOAuthProvider
from agent_penny.providers.google import GoogleProvider
from agent_penny.types import Calendar, CalendarEvent, MailMessageSnippet

pytestmark = pytest.mark.skipif(
    not os.path.exists("client_secrets.json"), reason="No client secrets file"
)

# Use the same OpenID scopes as the ExtendedGoogleOAuthProvider
# but add openid to work around an issue where it gets added by the backend and fails the frontend
SCOPES = ExtendedGoogleOAuthProvider().scopes + ["openid"]


def get_credentials() -> Credentials:
    creds = None
    if os.path.exists("credentials.json"):
        creds = Credentials.from_authorized_user_file("credentials.json", SCOPES)

    if creds and not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            logger.warning("Credential refresh failed", e)
            creds = None

    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
        creds = flow.run_local_server(
            port=8137,
            prompt="consent",  # Prompt is required to get a refresh token
        )

        with open("credentials.json", "w") as token:
            token.write(creds.to_json())

    return creds


@pytest.fixture
def provider() -> GoogleProvider:
    credentials = get_credentials()

    os.environ["OAUTH_GOOGLE_CLIENT_ID"] = credentials.client_id
    os.environ["OAUTH_GOOGLE_CLIENT_SECRET"] = credentials.client_secret

    return GoogleProvider(
        cl.User(
            identifier=getpass.getuser(),
            metadata={
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
            },
        )
    )


def test_calendar_list(provider: GoogleProvider):
    calendars = provider.calendar_list()
    assert calendars
    assert len(calendars) > 0

    ta = TypeAdapter(Calendar)
    for calendar in calendars:
        ta.validate_python(calendar)


def test_calendar_list_events(provider: GoogleProvider):
    events = provider.calendar_list_events(
        start_time=datetime.now() - timedelta(days=1),
        end_time=datetime.now(),
        users_iana_timezone="America/Vancouver",
    )

    assert events
    assert len(events) > 0

    ta = TypeAdapter(CalendarEvent)
    for event in events:
        ta.validate_python(event)


def test_calendar_list_events_not_found(provider: GoogleProvider):
    events = provider.calendar_list_events(
        start_time=datetime.fromisoformat("1990-01-01T00:00:00"),
        end_time=datetime.fromisoformat("1990-01-02T00:00:00"),
        users_iana_timezone="America/Vancouver",
        calendar_ids=["primary"],
    )

    assert events is not None
    assert len(events) == 0


def test_calendar_create_event(provider: GoogleProvider):
    tz = ZoneInfo("America/Vancouver")
    tomorrow = datetime.now(tz).date() + timedelta(days=1)

    event = provider.calendar_create_event(
        {
            "name": "Test Event",
            "start_time": datetime.combine(tomorrow, time(7), tz),
            "end_time": datetime.combine(tomorrow, time(8), tz),
            "calendar_id": "primary",
        }
    )

    try:
        assert event
        ta = TypeAdapter(CalendarEvent)
        ta.validate_python(event)
    finally:
        with provider.calendar_service() as calendar_service:
            calendar_service.events().delete(
                calendarId=event["calendar_id"], eventId=event["id"]
            ).execute()


def test_calendar_update_event(provider: GoogleProvider):
    if "TEST_GOOGLE_EVENT_ID" not in os.environ:
        pytest.skip("TEST_GOOGLE_EVENT_ID not defined")

    event_id = os.environ["TEST_GOOGLE_EVENT_ID"]

    tz = ZoneInfo("America/Vancouver")
    last_month = datetime.now(tz) - relativedelta(months=1)

    event = provider.calendar_update_event(
        {
            "id": event_id,
            "name": "Test Event",
            "start_time": last_month,
            "end_time": last_month + timedelta(hours=1),
            "description": f"Updated: {datetime.now().isoformat()}",
            "calendar_id": "primary",
        }
    )

    assert event
    ta = TypeAdapter(CalendarEvent)
    ta.validate_python(event)


def test_email_list_messages(provider: GoogleProvider):
    messages = provider.email_list_messages(max_results=10)

    assert messages
    assert len(messages) == 10

    ta = TypeAdapter(MailMessageSnippet)
    for message in messages:
        ta.validate_python(message)


def test_email_list_messages_not_found(provider: GoogleProvider):
    messages = provider.email_list_messages(query="from:agent-penny@007.com")

    assert messages is not None
    assert len(messages) == 0


def test_email_list_drafts(provider: GoogleProvider):
    drafts = provider.email_list_drafts()

    assert drafts

    logger.debug("Drafts", drafts=drafts)


@pytest.fixture
def draft_id() -> str:
    if "TEST_GOOGLE_DRAFT_ID" not in os.environ:
        pytest.skip("TEST_GOOGLE_DRAFT_ID not defined")

    return os.environ["TEST_GOOGLE_DRAFT_ID"]


def test_email_get_draft(provider: GoogleProvider, draft_id: str):
    draft = provider.email_get_draft(draft_id)

    assert draft

    logger.debug("Draft", draft=draft)


def test_email_update_draft(provider: GoogleProvider, draft_id: str):
    draft = provider.email_update_draft(
        draft_id,
        {
            "subject": "Test",
            "to": "agent-penny@007.com",
            "content": f"Updated: {datetime.now().isoformat()}",
        },
    )

    assert draft

    logger.debug("Updated draft", draft=draft)


def test_email_drafts(provider: GoogleProvider):
    draft = provider.email_create_draft(
        {
            "subject": "Test: Step 1",
            "to": "test@example.com",
            "content": "Hello, world!",
        }
    )

    draft_id = draft["id"]

    try:
        retrieved_draft = provider.email_get_draft(draft_id)
        assert retrieved_draft is not None
        assert retrieved_draft["id"] == draft_id
        assert retrieved_draft["message"]["subject"] == "Test: Step 1"
        assert retrieved_draft["message"]["to"] == "test@example.com"
        assert retrieved_draft["message"]["content"].strip() == "Hello, world!"

        drafts = provider.email_list_drafts()
        assert drafts
        assert any(d["id"] == draft_id for d in drafts)

        updated_draft = provider.email_update_draft(
            draft_id,
            {
                "subject": "Test: Step 2",
                "to": "quiz@example.com",
                "content": "The World says Hello",
            },
        )

        assert updated_draft is not None
        assert updated_draft["id"] == draft_id

        retrieved_draft = provider.email_get_draft(draft_id)
        assert retrieved_draft is not None
        assert retrieved_draft["id"] == draft_id
        assert retrieved_draft["message"]["subject"] == "Test: Step 2"
        assert retrieved_draft["message"]["to"] == "quiz@example.com"
        assert retrieved_draft["message"]["content"].strip() == "The World says Hello"
    finally:
        if draft_id:
            provider.email_delete_draft(draft_id)
        pass
