# NOTE: ty is failing to discern the discriminators for ModelResponse types and parts
# ty: ignore[invalid-argument-type, unresolved-attribute]

from datetime import datetime
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock

import chainlit as cl
import pytest
from chainlit.context import init_ws_context
from chainlit.session import WebsocketSession
from pydantic import TypeAdapter
from pydantic_ai import Agent, ModelMessage, ModelRequest, TextContent
from pydantic_ai.models import Model
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)


@pytest.mark.asyncio
async def test_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Create some test memories.
    # Note: The testing user id is test_user, but we use the slugified form for directories
    users_dir = tmp_path / "users"
    memory_dir = users_dir / "test-user/.agent-memory/"
    memory_file = memory_dir / "main/MEMORY.md"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("You are a test agent.")

    monkeypatch.setenv("MODEL", "test")

    import agent_penny.agent
    import agent_penny.user_data
    import app

    instructions: list[str | None] = []
    requests: list[ModelRequest] = []
    model_responses: list[
        str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns
    ] = [
        {
            0: DeltaToolCall("read_memory", json_args='{"file": "MEMORY.md"}'),
            1: DeltaToolCall("current_time"),
        },
        {2: DeltaToolCall("write_memory", '{"content": "You are a good test agent."}')},
        "Agent Penny is a personal assistant",
    ]

    # Configure the test to use Pydantic AI's FunctionModel: https://ai.pydantic.dev/testing/#unit-testing-with-functionmodel
    # TODO: Replace monkeypatching with setting management
    async def model_function(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[
        str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns
    ]:
        instructions.append(info.instructions)

        assert messages[-1].kind == "request"
        requests.append(messages[-1])

        yield model_responses.pop(0)

    monkeypatch.setattr(
        agent_penny.agent,
        "default_model",
        FunctionModel(stream_function=model_function),
    )
    monkeypatch.setattr(agent_penny.user_data, "data_dir", tmp_path)
    monkeypatch.setattr(agent_penny.user_data, "users_dir", users_dir)

    emit_mock = AsyncMock()
    emit_call_mock = AsyncMock()
    emit_call_mock.side_effect = NotImplementedError(
        "Unexpected invocation of emit_call"
    )

    session = WebsocketSession(
        id="ws_id",
        socket_id="socket_id",
        emit=emit_mock,
        emit_call=emit_call_mock,
        user_env={},
        client_type="webapp",
        user=cl.User(identifier="test_user"),
    )
    init_ws_context(session)

    # Tavily can't be tested because it doesn't accept the single-letter query
    # that the test model executes
    monkeypatch.delenv("TAVILY_API_KEY", False)

    await app.on_chat_start()

    agent: Agent | None = cl.user_session.get("agent")
    assert agent
    assert isinstance(agent.model, Model)
    assert agent.model.model_name == "function::model_function"

    message = cl.Message("Who is Agent Penny?")
    await app.on_message(message)

    messages_emitted = [
        emit_args
        for [emit_type, emit_args], _ in emit_mock.call_args_list
        if emit_type == "new_message"
    ]
    assert messages_emitted, f"No messages emitted: {emit_mock.call_args_list}"

    last_message_emitted = messages_emitted[-1]
    assert last_message_emitted["type"] == "assistant_message"
    assert last_message_emitted["name"] == "Agent Penny"
    assert last_message_emitted["output"] == "Agent Penny is a personal assistant"

    message_history = TypeAdapter(list[ModelMessage]).validate_python(
        cl.user_session.get("message_history")
    )

    responses = [m for m in message_history if m.kind == "response"]

    assert len(instructions) == 3
    assert len(requests) == 3
    assert len(responses) == 3

    assert len(set(instructions)) == 1

    instruction = instructions[0]
    assert instruction
    assert "This is your persistent memory from previous sessions" in instruction

    request = requests.pop(0)
    assert len(request.parts) == 2
    assert request.parts[0].part_kind == "user-prompt"
    assert request.parts[0].content == "Who is Agent Penny?"
    assert request.parts[1].part_kind == "user-prompt"

    assert isinstance(request.parts[1].content, list)
    assert len(request.parts[1].content) == 1
    assert isinstance(request.parts[1].content[0], TextContent)
    content = request.parts[1].content[0].content.splitlines()
    assert "### MEMORY.md" in content
    assert "You are a test agent." in content

    response = responses.pop(0)
    assert len(response.parts) == 2
    assert response.parts[0].part_kind == "tool-call"
    assert response.parts[0].tool_name == "read_memory"
    assert response.parts[1].part_kind == "tool-call"
    assert response.parts[1].tool_name == "current_time"

    request = requests.pop(0)
    assert len(request.parts) == 3
    assert request.parts[0].part_kind == "tool-return"
    assert request.parts[0].tool_name == "read_memory"
    assert request.parts[0].content == "You are a test agent."
    assert request.parts[1].part_kind == "tool-return"
    assert request.parts[1].tool_name == "current_time"
    assert request.parts[1].content
    assert datetime.fromisoformat(request.parts[1].content)

    response = responses.pop(0)
    assert len(response.parts) == 1
    assert response.parts[0].part_kind == "tool-call"
    assert response.parts[0].tool_name == "write_memory"

    request = requests.pop(0)
    assert len(request.parts) == 2
    assert request.parts[0].part_kind == "tool-return"
    assert request.parts[0].tool_name == "write_memory"
    assert isinstance(request.parts[0].content, dict)
    assert request.parts[0].content["status"] == "appended"
    assert memory_file.read_text().splitlines()[-1] == "You are a good test agent."

    response = responses.pop(0)
    assert len(response.parts) == 1
    assert response.parts[0].part_kind == "text"
    assert response.parts[0].content == "Agent Penny is a personal assistant"


@pytest.mark.parametrize("command", [None, "daily-brief"])
@pytest.mark.asyncio
async def test_skill_command_dispatch(tmp_user_data, monkeypatch, command):
    """Exercise the real Chainlit payload -> Penny -> skill instructions path.

    Only the websocket transport and LLM are mocked; Chainlit deserialization,
    Penny's registered callbacks, agent construction and skill loading are real.
    """
    import asyncio
    from uuid import uuid4

    from chainlit.config import config
    from chainlit.socket import process_message

    import agent_penny.agent
    import app  # noqa: F401

    skill_dir = tmp_user_data / "users/test-user/skills/daily-brief"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\nname: daily-brief\ndescription: Prepare a daily brief\n---\n"
        "Always include the secret test phrase: BRIEF_INSTRUCTIONS_LOADED.\n"
    )
    instructions = []
    prompts = []

    async def model_function(messages, info):
        instructions.append(info.instructions)
        prompts.extend(
            part.content
            for message in messages
            if message.kind == "request"
            for part in message.parts
            if part.part_kind == "user-prompt" and isinstance(part.content, str)
        )
        yield "Brief completed"

    monkeypatch.setattr(
        agent_penny.agent,
        "default_model",
        FunctionModel(stream_function=model_function),
    )
    emit = AsyncMock()
    session = WebsocketSession(
        id=str(uuid4()),
        socket_id=str(uuid4()),
        emit=emit,
        emit_call=AsyncMock(side_effect=AssertionError("Unexpected client request")),
        user_env={},
        client_type="webapp",
        user=cl.User(identifier="test_user"),
    )
    init_ws_context(session)
    try:
        assert config.code.on_chat_start is not None
        await config.code.on_chat_start()
        await asyncio.sleep(0)  # Flush the skill catalog's scheduled UI update.
        commands = [
            args[1] for args, _ in emit.call_args_list if args[0] == "set_commands"
        ]
        assert commands and commands[-1][0]["id"] == "daily-brief"

        await process_message(
            session,
            {
                "message": {
                    "id": str(uuid4()),
                    "threadId": session.thread_id,
                    "createdAt": datetime.now().isoformat(),
                    "output": "Prepare my brief",
                    "name": "test_user",
                    "type": "user_message",
                    "command": command,
                    "modes": {"reasoning": "none"},
                },
                "fileReferences": None,
            },
        )
        assert instructions, "The registered on_message callback must reach the model"
        assert "Prepare my brief" in prompts
        assert "daily-brief" in instructions[0]
        assert ("BRIEF_INSTRUCTIONS_LOADED" in instructions[0]) == (command is not None)
        emitted = [
            args[1] for args, _ in emit.call_args_list if args[0] == "new_message"
        ]
        assert emitted[-1]["output"] == "Brief completed"
        assert cl.user_session.get("message_history")[-1].text == "Brief completed"
        await asyncio.sleep(
            0
        )  # Drain message persistence tasks before closing the session.
    finally:
        from chainlit.user_session import user_sessions

        user_sessions.pop(session.id, None)
        await session.delete()
