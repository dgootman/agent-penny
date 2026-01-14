import dataclasses
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import chainlit as cl
from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
)


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

memory_file = data_dir / "memories.txt"
if not memory_file.exists():
    memory_file.write_text("")


def current_date(iana_timezone: str | None = None) -> str:
    return datetime.now(
        tz=ZoneInfo(iana_timezone) if iana_timezone else None
    ).isoformat()


def load_memory():
    """Load the agent's persistent memory of key details from past conversations."""

    return memory_file.read_text()


def save_memory(memory: str):
    """
    Persist the agent's memory of key details that may impact future conversations.
    When adding new memory, retain all existing essential information, and remove outdated or inconsistent details to keep memory concise and accurate.
    """

    memory_file.write_text(memory)


@cl.on_chat_start
async def on_chat_start():
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
