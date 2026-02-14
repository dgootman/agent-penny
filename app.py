import getpass
import os
from datetime import datetime
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

import chainlit as cl
from chainlit.config import config as cl_config
from chainlit.input_widget import InputWidget, Select, Switch
from chainlit.oauth_providers import providers as oauth_providers
from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelSettings,
    PartEndEvent,
    RetryPromptPart,
    ToolReturnPart,
)
from pydantic_ai.models.bedrock import BedrockModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from starlette.datastructures import Headers
from ua_parser import parse_user_agent

from agent_penny import audio
from agent_penny.audio import StreamingTranscriber
from agent_penny.auth.google import ExtendedGoogleOAuthProvider
from agent_penny.logging import json_log_sink
from agent_penny.providers.google import GoogleProvider
from agent_penny.tools.memory import MemoryProvider
from agent_penny.tools.perplexity import perplexity

logger.remove()
logger.add(json_log_sink)

default_model = os.environ["MODEL"]
default_thinking = os.environ.get("THINKING") == "true"
google_auth_enabled = bool(os.environ.get("OAUTH_GOOGLE_CLIENT_ID"))

if google_auth_enabled:
    logger.debug("Google mode")

    # Replace the OAuth providers with the ExtendedGoogleOAuthProvider
    oauth_providers.clear()
    oauth_providers.append(ExtendedGoogleOAuthProvider())

    @cl.oauth_callback
    async def oauth_callback(
        provider_id: str,
        token: str,
        raw_user_data: dict[str, str],
        default_user: cl.User,
        id_token: str | None = None,
    ) -> cl.User | None:
        with logger.contextualize(user_id=default_user.identifier):
            logger.debug("User logged in", provider_id=provider_id)
            return default_user

else:
    logger.debug("Standalone mode")

    @cl.header_auth_callback
    async def header_auth_callback(headers: Headers) -> cl.User | None:
        return cl.User(
            identifier=getpass.getuser(), metadata={"provider": "standalone"}
        )


def get_user() -> cl.User:
    user: cl.User | None = cl.user_session.get("user")
    assert user
    return user


def current_date(iana_timezone: str | None = None) -> str:
    return datetime.now(
        tz=ZoneInfo(iana_timezone) if iana_timezone else None
    ).isoformat()


@cl.set_starters
async def set_starters(user: cl.User | None):
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


class AgentConfig(TypedDict):
    model: str
    model_settings: ModelSettings | None


def agent_config(
    model: str | None = None,
    thinking: bool | None = None,
) -> AgentConfig:
    model = model or default_model
    thinking = thinking if thinking is not None else default_thinking

    model_settings: ModelSettings | None = None

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
        elif llm_provider == "google-gla":
            model_settings = GoogleModelSettings(
                google_thinking_config={"include_thoughts": True}
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
            raise ValueError(f"Thinking is not supported for provider: {llm_provider}")

    return {
        "model": model,
        "model_settings": model_settings,
    }


@cl.on_chat_start
async def on_chat_start():
    user = get_user()

    with logger.contextualize(user_id=user.identifier):
        logger.debug("Chat started")

        available_models_by_provider = {
            "bedrock": [  # https://platform.claude.com/docs/en/about-claude/models/overview
                "bedrock:us.anthropic.claude-opus-4-6-v1",
                "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0",
            ],
            "openai": [  # https://developers.openai.com/api/docs/models
                "openai:gpt-5.2",
                "openai:gpt-5-mini",
                "openai:gpt-5-nano",
            ],
            "google-gla": [  # https://ai.google.dev/gemini-api/docs/models
                "google-gla:gemini-3-pro-preview",
                "google-gla:gemini-3-flash-preview",
                "google-gla:gemini-2.5-pro",
                "google-gla:gemini-2.5-flash",
                "google-gla:gemini-2.5-flash-lite",
            ],
        }

        llm_provider = default_model.split(":", 1)[0]

        setting_inputs: list[InputWidget] = []

        available_models = available_models_by_provider.get(llm_provider, [])
        if available_models:
            if default_model not in available_models:
                available_models.append(default_model)

            setting_inputs.append(
                Select(
                    id="model",
                    label="Model",
                    values=available_models,
                    initial_index=available_models.index(default_model),
                )
            )

        setting_inputs.append(
            Switch(
                id="thinking",
                label="Thinking",
                initial=default_thinking,
            )
        )

        await cl.ChatSettings(setting_inputs).send()

        memory = MemoryProvider(user)
        tools = [current_date, *memory.tools]

        if google_auth_enabled:
            provider = GoogleProvider(user)
            tools += provider.tools

        if "PERPLEXITY_API_KEY" in os.environ:
            tools.append(perplexity)

        config = agent_config()

        logger.debug(
            "Creating agent",
            **config,
            tools=[str(t) for t in tools],
        )

        agent = Agent(
            **config,
            tools=tools,  # type: ignore[arg-type]
            system_prompt=[
                f"You know the following from previous conversations: {memory.load_memory()}"
            ],
        )
        cl.user_session.set("agent", agent)


@cl.on_message
@logger.catch
async def on_message(message: cl.Message):
    user = get_user()
    chat_settings: dict[str, Any] | None = cl.user_session.get("chat_settings")

    steps: dict[str, cl.Step] = {}

    with logger.contextualize(
        user_id=user.identifier, message_id=message.id, chat_settings=chat_settings
    ):
        try:
            logger.debug("Message received")

            agent: Agent = cl.user_session.get("agent")

            message_history = cl.user_session.get("message_history", [])

            logger.trace(
                "Message received",
                message=message.to_dict(),
                message_history=message_history,
            )

            if chat_settings and (
                ("model" in chat_settings and chat_settings["model"] != default_model)
                or (
                    "thinking" in chat_settings
                    and chat_settings["thinking"] != default_thinking
                )
            ):
                config = agent_config(
                    chat_settings.get("model"), chat_settings.get("thinking")
                )
                stream = agent.run_stream_events(
                    message.content,
                    message_history=message_history,
                    **config,
                )
            else:
                stream = agent.run_stream_events(
                    message.content,
                    message_history=message_history,
                )

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

                    if isinstance(event.result, ToolReturnPart):
                        step.output = {"output": event.result.model_response_object()}
                    elif isinstance(event.result, RetryPromptPart):
                        step.is_error = True
                        step.output = {"error": event.result.model_response()}

                    await step.__aexit__(None, None, None)

        except Exception as e:
            for step in steps.values():
                await step.__aexit__(type(e), e, e.__traceback__)

            # TODO: Sanitize exceptions
            await cl.Message(f"⚠️ **Error**: {type(e).__name__}: {e}").send()
            raise e


if "WHISPER_MODEL" in os.environ:
    assert cl_config.features.audio is not None

    cl_config.features.audio.enabled = True

    # Prime the Whisper Model cache
    audio.whisper_model()

    @cl.on_audio_start
    async def on_audio_start():
        user = get_user()

        with logger.contextualize(user_id=user.identifier):
            logger.debug("Audio started")

            # Firefox can't override the microphone's sample rate, so we have to adapt to the original sample rate
            user_agent_header = cl.context.session.environ["HTTP_USER_AGENT"]
            user_agent = parse_user_agent(user_agent_header)
            sample_rate = (
                16000 if not user_agent or user_agent.family != "Firefox" else 44000
            )

            cl.user_session.set("transcriber", StreamingTranscriber(sample_rate))

            return True

    async def on_transcription(text: str) -> None:
        message = cl.Message(type="user_message", content=text)

        await message.send()
        await on_message(message)

    @cl.on_audio_chunk
    async def on_audio_chunk(chunk: cl.InputAudioChunk):
        user = get_user()

        with logger.contextualize(user_id=user.identifier):
            assert chunk.mimeType == "pcm16"

            transcriber: StreamingTranscriber = cl.user_session.get("transcriber")
            text = await transcriber.add_chunk(chunk.data)
            if text:
                await on_transcription(text)

    @cl.on_audio_end
    async def on_audio_end():
        user = get_user()

        with logger.contextualize(user_id=user.identifier):
            logger.debug("Audio ended")

            transcriber: StreamingTranscriber = cl.user_session.get("transcriber")
            text = await transcriber.transcribe()
            if text:
                await on_transcription(text)
