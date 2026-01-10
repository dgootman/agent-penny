import os

import chainlit as cl
from pydantic_ai import Agent, AgentRunResultEvent

agent = Agent(os.environ["MODEL"])


@cl.on_message
async def main(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])

    stream = agent.run_stream_events(message.content, message_history=message_history)

    async for event in stream:
        if isinstance(event, AgentRunResultEvent):
            await cl.Message(event.result.output).send()
            cl.user_session.set("message_history", event.result.all_messages())
