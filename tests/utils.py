from typing import Any, Awaitable, Callable
from unittest.mock import AsyncMock
from uuid import uuid4

import chainlit as cl
from chainlit.context import init_ws_context
from chainlit.session import WebsocketSession


async def init_chainlit_context(
    emit: Callable[[str, Any], Awaitable[None]] | None = None,
):
    emit_call_mock = AsyncMock()
    emit_call_mock.side_effect = NotImplementedError(
        "Unexpected invocation of emit_call"
    )

    session = WebsocketSession(
        id=f"session-{uuid4()}",
        socket_id=f"socket-{uuid4()}",
        emit=emit or AsyncMock(),  # type: ignore[ty:invalid-argument-type]
        emit_call=emit_call_mock,
        user_env={},
        client_type="webapp",
        user=cl.User(identifier="test_user"),
    )
    init_ws_context(session)
