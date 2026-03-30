import asyncio
import getpass
import os
from typing import Any
from uuid import uuid4

import chainlit as cl
import logfire
from chainlit.config import config as cl_config
from chainlit.input_widget import InputWidget, Select, Switch, TextInput
from chainlit.oauth_providers import providers as oauth_providers
from chainlit.types import ThreadDict
from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartEndEvent,
    RetryPromptPart,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from starlette.datastructures import Headers
from ua_parser import parse_user_agent

from agent_penny import user_data
from agent_penny.agent import agent_config
from agent_penny.agent import create as agent_create
from agent_penny.auth.google import ExtendedGoogleOAuthProvider
from agent_penny.chainlit_utils import get_user
from agent_penny.data import LocalDataLayer
from agent_penny.logging import json_log_sink

if os.environ.get("CONVERSATION_HISTORY_ENABLED") == "true":
    # HACK: kokoro reinitializes loguru. Import it first then apply the logger config
    import kokoro  # type: ignore[import-untyped] # noqa: F401

logger.remove()
logger.add(json_log_sink)

logfire.configure(
    service_name=os.environ.get("OTEL_SERVICE_NAME", "agent-penny"),
    # Do not send traces to logfire by default
    send_to_logfire=os.environ.get("LOGFIRE_SEND_TO_LOGFIRE") == "true",
)
logfire.instrument_pydantic_ai()
logfire.instrument_httpx()
logfire.instrument_requests()

default_model = os.environ["MODEL"]
default_thinking = os.environ.get("THINKING") == "true"
google_auth_enabled = bool(os.environ.get("OAUTH_GOOGLE_CLIENT_ID"))
audio_input_enabled = "WHISPER_MODEL" in os.environ
conversation_history_enabled = os.environ.get("CONVERSATION_HISTORY_ENABLED") == "true"


@cl.on_app_startup
@logfire.instrument()
async def on_app_startup():
    logger.debug("App started")

    if audio_input_enabled:
        from agent_penny.audio import kokoro_model, whisper_model

        assert cl_config.features.audio is not None

        cl_config.features.audio.enabled = True

        # Prime the audio model caches in the background
        asyncio.create_task(asyncio.to_thread(whisper_model))
        asyncio.create_task(asyncio.to_thread(kokoro_model))


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


@cl.set_starters
async def set_starters(user: cl.User | None):
    return [
        cl.Starter(
            label="📝 Daily Brief",
            message="Create a daily brief",
        ),
        cl.Starter(
            label="📅 Today's Calendar",
            message="What's on my calendar today?",
        ),
        cl.Starter(
            label="✉️ Mail Summary",
            message="Summarize the latest 10 e-mails.",
        ),
    ]


async def render_settings():
    env_vars_by_provider = {
        "anthropic": "ANTHROPIC_API_KEY",
        "bedrock": "BEDROCK_ENABLE",  # Bedrock uses AWS credentials, which have different ways of being provisioned
        "openai": "OPENAI_API_KEY",
        "google-gla": "GOOGLE_API_KEY",
    }

    available_models_by_provider = {
        "anthropic": [  # https://platform.claude.com/docs/en/about-claude/models/overview
            "anthropic:claude-opus-4-6",
            "anthropic:claude-sonnet-4-6",
            "anthropic:claude-haiku-4-5-20251001",
        ],
        "bedrock": [  # https://platform.claude.com/docs/en/about-claude/models/overview
            "bedrock:us.anthropic.claude-opus-4-6-v1",
            "bedrock:us.anthropic.claude-sonnet-4-6",
            "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0",
        ],
        "google-gla": [  # https://ai.google.dev/gemini-api/docs/models
            "google-gla:gemini-3.1-pro-preview",
            "google-gla:gemini-3-pro-preview",
            "google-gla:gemini-3-flash-preview",
            "google-gla:gemini-2.5-pro",
            "google-gla:gemini-2.5-flash",
            "google-gla:gemini-2.5-flash-lite",
        ],
        "openai": [  # https://developers.openai.com/api/docs/models
            "openai:gpt-5.2",
            "openai:gpt-5-mini",
            "openai:gpt-5-nano",
        ],
    }

    user_settings = user_data.load_settings()
    user_model = user_settings.get("model") or default_model

    setting_inputs: list[InputWidget] = []

    available_models = [
        model
        for provider, key in env_vars_by_provider.items()
        if os.environ.get(key)
        for model in available_models_by_provider.get(provider, [])
    ]

    if available_models:
        setting_inputs.append(
            Select(
                id="model",
                label="Model",
                values=available_models,
                initial_value=user_model,
            )
        )

    setting_inputs.append(
        TextInput(
            id="custom_model",
            label="Custom Model",
            initial=None if user_model in available_models else user_model,
        )
    )

    setting_inputs.append(
        Switch(
            id="thinking",
            label="Thinking",
            initial=user_settings["thinking"]
            if "thinking" in user_settings
            else default_thinking,
        )
    )

    await cl.ChatSettings(setting_inputs).send()


if conversation_history_enabled:
    logger.warning("Conversation history is a work in progress")

    @cl.data_layer
    def get_data_layer():
        return LocalDataLayer()


async def prepare_chat():
    await render_settings()

    agent = agent_create()
    cl.user_session.set("agent", agent)


@cl.on_chat_start
@logfire.instrument()
async def on_chat_start():
    user = get_user()

    with logger.contextualize(user_id=user.identifier):
        logger.debug("Chat started")

        await prepare_chat()


if conversation_history_enabled:

    @cl.on_chat_resume
    @logfire.instrument()
    async def on_chat_resume(thread: ThreadDict):
        user = get_user()

        with logger.contextualize(user_id=user.identifier):
            logger.debug(
                "Chat resumed",
                thread={k: v for k, v in thread.items() if k in ["id", "name"]},
            )

            await prepare_chat()

            message_history: list[ModelMessage] = []

            for step in thread["steps"]:
                if step["type"] == "user_message":
                    message_history.append(
                        ModelRequest([UserPromptPart(content=step["output"])])
                    )
                elif step["type"] == "assistant_message":
                    message_history.append(ModelResponse([TextPart(step["output"])]))

            cl.user_session.set("message_history", message_history)


@cl.on_settings_update
@logfire.instrument()
async def on_settings_update(chat_settings: dict[str, Any]):
    user = get_user()

    with logger.contextualize(user_id=user.identifier):
        logger.debug("Settings updated", chat_settings=chat_settings)

        custom_model = chat_settings.pop("custom_model", None)
        if custom_model:
            chat_settings["model"] = custom_model

        # TODO: Validate that chat settings match the user-setting structure
        user_data.save_settings(chat_settings)  # type: ignore[arg-type]

        # Custom model handling affects setting rendering
        # by setting the model to blank if a custom model is provided
        if custom_model:
            await render_settings()


@cl.on_message
@logger.catch
@logfire.instrument()
async def on_message(message: cl.Message):
    user = get_user()
    user_settings = user_data.load_settings()

    steps: dict[str, cl.Step] = {}

    with logger.contextualize(
        user_id=user.identifier, message_id=message.id, user_settings=user_settings
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

            if (
                "model" in user_settings and user_settings["model"] != default_model
            ) or (
                "thinking" in user_settings
                and user_settings["thinking"] != default_thinking
            ):
                config = agent_config(
                    user_settings.get("model"), user_settings.get("thinking")
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


if audio_input_enabled:
    from agent_penny.audio import StreamingTranscriber, text_to_speech

    @cl.on_audio_start
    @logfire.instrument()
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

    @logfire.instrument()
    async def on_transcription(text: str) -> None:
        message = cl.Message(type="user_message", content=text)

        await message.send()
        await on_message(message)

        message_history: list[ModelMessage] = cl.user_session.get("message_history", [])
        last_message = message_history[-1]

        if last_message.kind == "response" and last_message.text:
            track_id = str(uuid4())
            cl.user_session.set("track_id", str(track_id))

            speech = text_to_speech(last_message.text)
            for chunk in speech:
                await cl.context.emitter.send_audio_chunk(
                    cl.OutputAudioChunk(
                        mimeType="pcm16",
                        data=chunk,
                        track=track_id,
                    )
                )

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
    @logfire.instrument()
    async def on_audio_end():
        user = get_user()

        with logger.contextualize(user_id=user.identifier):
            logger.debug("Audio ended")

            transcriber: StreamingTranscriber = cl.user_session.get("transcriber")
            text = await transcriber.transcribe()
            if text:
                await on_transcription(text)
