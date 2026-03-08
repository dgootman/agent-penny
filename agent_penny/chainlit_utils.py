import chainlit as cl


def get_user() -> cl.User:
    user: cl.User | None = cl.user_session.get("user")
    assert user
    return user
