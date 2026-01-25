import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import chainlit as cl
from chainlit.oauth_providers import GoogleOAuthProvider
from chainlit.oauth_providers import providers as oauth_providers
from fastapi import Request, Response
from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartEndEvent,
)
from pydantic_ai.models.bedrock import BedrockModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from slugify import slugify

from agent_penny.logging import json_log_sink
from agent_penny.providers.google import GoogleProvider

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
                "https://www.googleapis.com/auth/calendar.events.owned",
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


@cl.on_logout
async def on_logout(request: Request, response: Response):
    user: cl.User = cl.user_session.get("user")
    logger.debug("User logged out", user_id=user)


def current_date(iana_timezone: str | None = None) -> str:
    return datetime.now(
        tz=ZoneInfo(iana_timezone) if iana_timezone else None
    ).isoformat()


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="📅 Today's Calendar",
            message="What's on my calendar today?",
        ),
        cl.Starter(
            label="✉️ Mail Summary",
            message="Summarize the latest 10 e-mails.",
        ),
    ]


@cl.on_chat_start
async def on_chat_start():
    user: cl.User = cl.user_session.get("user")

    with logger.contextualize(user_id=user.identifier):
        logger.debug("Chat started")

        provider = GoogleProvider(user)

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

        tools = [current_date, load_memory, save_memory, *provider.tools]

        if "PERPLEXITY_API_KEY" in os.environ:
            from agent_penny.tools.perplexity import perplexity

            tools.append(perplexity)

        model = os.environ["MODEL"]
        thinking = os.environ.get("THINKING") == "true"
        model_settings = None

        if thinking:
            # See: https://ai.pydantic.dev/thinking/
            # TODO: Make model settings for thinking configurable
            llm_provider, model_id = model.split(":", 1)
            if llm_provider == "openai":
                # Upgrade to the OpenAI Responses API: https://platform.openai.com/docs/guides/migrate-to-responses
                model = f"openai-responses:{model_id}"
                model_settings = OpenAIResponsesModelSettings(
                    openai_reasoning_effort="low",
                    openai_reasoning_summary="detailed",
                )
            elif llm_provider == "bedrock":
                if model_id.startswith("us.anthropic."):
                    model_settings = BedrockModelSettings(
                        bedrock_additional_model_requests_fields={
                            "thinking": {"type": "enabled", "budget_tokens": 4000}
                        }
                    )
                else:
                    raise ValueError(
                        f"Thinking is not supported for Bedrock model: {model_id}"
                    )
            else:
                raise ValueError(
                    f"Thinking is not supported for provider: {llm_provider}"
                )

        logger.debug(
            "Creating agent",
            model=model,
            model_settings=model_settings,
            thinking=thinking,
            tools=[str(t) for t in tools],
        )

        agent = Agent(
            model,
            model_settings=model_settings,
            tools=tools,
            system_prompt=[
                f"You know the following from previous conversations: {load_memory()}"
            ],
        )
        cl.user_session.set("agent", agent)


@cl.on_message
@logger.catch
async def on_message(message: cl.Message):
    user: cl.User = cl.user_session.get("user")

    steps = None

    with logger.contextualize(user_id=user.identifier, message_id=message.id):
        try:
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

                if isinstance(event, PartEndEvent):
                    if event.part.part_kind == "thinking":
                        async with cl.Step(
                            "Thinking", type="llm", id=event.part.id
                        ) as step:
                            step.output = event.part.content
                    elif event.part.part_kind == "text":
                        async with cl.Step(
                            "Text", type="llm", id=event.part.id
                        ) as step:
                            step.output = event.part.content

                elif isinstance(event, FunctionToolCallEvent):
                    step = cl.Step(
                        event.part.tool_name, type="tool", id=event.tool_call_id
                    )
                    step.input = {"input": event.part.args_as_dict()}

                    steps[event.tool_call_id] = step

                    await step.__aenter__()

                elif isinstance(event, FunctionToolResultEvent):
                    step = steps.pop(event.tool_call_id)
                    step.output = {"output": event.result.model_response_object()}

                    await step.__aexit__(None, None, None)

        except Exception as e:
            if steps:
                for step in steps.values():
                    await step.__aexit__(type(e), e, e.__traceback__)

            # TODO: Sanitize exceptions
            await cl.Message(f"⚠️ **Error**: {type(e).__name__}: {e}").send()
            raise e
