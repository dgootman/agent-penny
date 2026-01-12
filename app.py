import os
from datetime import datetime
from zoneinfo import ZoneInfo

import chainlit as cl
from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
)


def current_date(iana_timezone: str | None = None) -> str:
    return datetime.now(
        tz=ZoneInfo(iana_timezone) if iana_timezone else None
    ).isoformat()


@cl.on_chat_start
async def on_chat_start():
    model = os.environ["MODEL"]
    logger.debug("Creating agent", model=model)

    agent = Agent(model, tools=[current_date])
    cl.user_session.set("agent", agent)


@cl.on_message
async def main(message: cl.Message):
    agent: Agent = cl.user_session.get("agent")

    message_history = cl.user_session.get("message_history", [])

    logger.trace({"message": message.to_dict(), "message_history": message_history})

    stream = agent.run_stream_events(message.content, message_history=message_history)

    steps: dict[str, cl.Step] = {}

    async for event in stream:
        logger.trace({"event": event})

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
