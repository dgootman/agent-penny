import os
from datetime import datetime
from zoneinfo import ZoneInfo

import chainlit as cl
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


agent = Agent(os.environ["MODEL"], tools=[current_date])


@cl.on_message
async def main(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])

    stream = agent.run_stream_events(message.content, message_history=message_history)

    steps: dict[str, cl.Step] = {}

    async for event in stream:
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
