import dataclasses
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import chainlit as cl
from chainlit.oauth_providers import GoogleOAuthProvider
from chainlit.oauth_providers import providers as oauth_providers
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
)
from slugify import slugify


def default_json(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj):
        return {"__type": type(obj).__name__} | dataclasses.asdict(obj)

    # Write warning directly to stderr if the object could not be serialized
    # Don't use `logger` to avoid recursion since `json_log_sink` uses this function
    if os.environ.get("LOGURU_LEVEL") == "TRACE":
        warning = json.dumps(
            {
                "time": datetime.now().isoformat(),
                "level": "WARNING",
                "message": f"Cannot serialize object of type: {type(obj)}",
            }
        )
        sys.stderr.write(f"{warning}\n")

    return str(obj)


def to_json(obj):
    return json.dumps(obj, default=default_json, ensure_ascii=False)


def json_log_sink(message):
    record = message.record
    text = to_json(
        {
            "time": record["time"],
            "thread": f"{record['thread'].name}({record['thread'].id})",
            "level": record["level"].name,
            "message": record["message"],
        }
        | ({"context": record["extra"]} if record["extra"] else {})
        | ({"exception": record["exception"]} if record["exception"] else {}),
    )
    sys.stderr.write(f"{text}\n")


logger.remove()
logger.add(json_log_sink)

data_dir = Path(os.environ.get("DATA_DIR", "~/.local/share/agent-penny")).expanduser()
data_dir.mkdir(parents=True, exist_ok=True)


class ExtendedGoogleOAuthProvider(GoogleOAuthProvider):
    def __init__(self):
        super().__init__()

        # Add Gmail and Calendar to authentication scope
        self.authorize_params["scope"] = " ".join(
            {
                *self.authorize_params["scope"].split(" "),
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
            }
        )

        # Add consent prompt to receive refresh token
        self.authorize_params["prompt"] = "consent"

        self.refresh_token = None

    async def get_raw_token_response(self, code: str, url: str) -> dict:
        if self.refresh_token is not None:
            raise RuntimeError("Refresh token shouldn't be set")

        response = await super().get_raw_token_response(code, url)
        self.refresh_token = response["refresh_token"]

        return response

    async def get_user_info(self, token: str) -> tuple[dict[str, str], cl.User]:
        if self.refresh_token is None:
            raise RuntimeError("Refresh token not set")

        (google_user, user) = await super().get_user_info(token)

        user.metadata["token"] = token
        user.metadata["refresh_token"] = self.refresh_token

        self.refresh_token = None

        return google_user, user


# Replace the OAuth providers with the ExtendedGoogleOAuthProvider
oauth_providers.clear()
oauth_providers.append(ExtendedGoogleOAuthProvider())


@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict[str, str],
    default_user: cl.User,
) -> cl.User | None:
    with logger.contextualize(user_id=default_user.identifier):
        logger.debug("User logged in", provider_id=provider_id)
        return default_user


def current_date(iana_timezone: str | None = None) -> str:
    return datetime.now(
        tz=ZoneInfo(iana_timezone) if iana_timezone else None
    ).isoformat()


@cl.on_chat_start
async def on_chat_start():
    user: cl.User = cl.user_session.get("user")

    with logger.contextualize(user_id=user.identifier):
        logger.debug("Chat started")

        token = user.metadata["token"]
        refresh_token = user.metadata["refresh_token"]

        credentials = Credentials(token, refresh_token=refresh_token)
        oauth2_service = build("oauth2", "v2", credentials=credentials)
        token_info = oauth2_service.tokeninfo().execute()

        logger.debug("Token info", token_info=token_info)

        user_data_dir = data_dir / slugify(user.identifier)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        memory_file = user_data_dir / "memories.txt"
        if not memory_file.exists():
            memory_file.write_text("")

        def load_memory():
            """Load the agent's persistent memory of key details from past conversations."""

            return memory_file.read_text()

        def save_memory(memory: str):
            """
            Persist long-term agent memory that may affect future conversations.

            Workflow:
            - Always call `load_memory` first.
            - Merge existing memory with new information.
            - Resolve conflicts and remove outdated details.
            - Call `save_memory` with the full merged memory.

            Guidelines:
            - Retain all relevant information.
            - This overwrites prior memory; never save partial updates.
            - Keep memory accurate, consistent, and concise.
            """

            memory_file.write_text(memory)

        model = os.environ["MODEL"]
        logger.debug("Creating agent", model=model)

        agent = Agent(
            model,
            tools=[
                current_date,
                load_memory,
                save_memory,
            ],
            system_prompt=[
                f"You know the following from previous conversations: {load_memory()}"
            ],
        )
        cl.user_session.set("agent", agent)


@cl.on_message
async def on_message(message: cl.Message):
    user: cl.User = cl.user_session.get("user")

    with logger.contextualize(user_id=user.identifier, message_id=message.id):
        logger.debug("Message received")

        agent: Agent = cl.user_session.get("agent")

        message_history = cl.user_session.get("message_history", [])

        logger.trace(
            "Message received",
            message=message.to_dict(),
            message_history=message_history,
        )

        stream = agent.run_stream_events(
            message.content, message_history=message_history
        )

        steps: dict[str, cl.Step] = {}

        async for event in stream:
            logger.trace("Event received", event=event)

            if isinstance(event, AgentRunResultEvent):
                await cl.Message(event.result.output).send()
                cl.user_session.set("message_history", event.result.all_messages())

            elif isinstance(event, FunctionToolCallEvent):
                step = cl.Step(event.part.tool_name, type="tool", id=event.tool_call_id)
                step.input = {"input": event.part.args_as_dict()}

                steps[event.tool_call_id] = step

                await step.__aenter__()

            elif isinstance(event, FunctionToolResultEvent):
                step = steps[event.tool_call_id]
                step.output = {"output": event.result.model_response_object()}

                await step.__aexit__(None, None, None)
