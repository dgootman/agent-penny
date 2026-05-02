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
from pydantic_ai import Agent, ModelMessage, ModelRequest
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
    user_dir = users_dir / "test-user"
    user_dir.mkdir(parents=True)
    memory_file = user_dir / "memories.txt"
    memory_file.write_text("You are a test agent.")

    monkeypatch.setenv("MODEL", "test")

    import agent_penny.agent
    import agent_penny.user_data
    import app

    requests: list[ModelRequest] = []
    model_responses: list[
        str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns
    ] = [
        {0: DeltaToolCall("load_memory"), 1: DeltaToolCall("current_date")},
        {2: DeltaToolCall("save_memory", '{"memory": "You are a good test agent."}')},
        "Agent Penny is a personal assistant",
    ]

    # Configure the test to use Pydantic AI's FunctionModel: https://ai.pydantic.dev/testing/#unit-testing-with-functionmodel
    # TODO: Replace monkeypatching with setting management
    async def model_function(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[
        str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns
    ]:
        assert messages[-1].kind == "request"
        requests.append(messages[-1])

        yield model_responses.pop(0)

    monkeypatch.setattr(
        agent_penny.agent,
        "default_model",
        FunctionModel(stream_function=model_function),
    )
    monkeypatch.setattr(agent_penny.agent, "default_thinking", False)
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

    assert len(requests) == 3
    assert len(responses) == 3

    request = requests.pop(0)
    assert len(request.parts) == 2
    assert request.parts[0].part_kind == "system-prompt"
    assert (
        request.parts[0].content
        == "You know the following from previous conversations: You are a test agent."
    )
    assert request.parts[1].part_kind == "user-prompt"
    assert request.parts[1].content == "Who is Agent Penny?"

    response = responses.pop(0)
    assert len(response.parts) == 2
    assert response.parts[0].part_kind == "tool-call"
    assert response.parts[0].tool_name == "load_memory"
    assert response.parts[1].part_kind == "tool-call"
    assert response.parts[1].tool_name == "current_date"

    request = requests.pop(0)
    assert len(request.parts) == 2
    assert request.parts[0].part_kind == "tool-return"
    assert request.parts[0].tool_name == "load_memory"
    assert request.parts[0].content == "You are a test agent."
    assert request.parts[1].part_kind == "tool-return"
    assert request.parts[1].tool_name == "current_date"
    assert request.parts[1].content
    assert datetime.fromisoformat(request.parts[1].content)

    response = responses.pop(0)
    assert len(response.parts) == 1
    assert response.parts[0].part_kind == "tool-call"
    assert response.parts[0].tool_name == "save_memory"

    request = requests.pop(0)
    assert len(request.parts) == 1
    assert request.parts[0].part_kind == "tool-return"
    assert request.parts[0].tool_name == "save_memory"
    assert request.parts[0].content is None
    assert memory_file.read_text() == "You are a good test agent."

    response = responses.pop(0)
    assert len(response.parts) == 1
    assert response.parts[0].part_kind == "text"
    assert response.parts[0].content == "Agent Penny is a personal assistant"
