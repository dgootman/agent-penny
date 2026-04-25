import asyncio
import os

import logfire
from aiogram import Bot, Dispatcher, html
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from loguru import logger

dp = Dispatcher()


@dp.message(CommandStart())
@logfire.instrument(new_trace=True)
async def on_start(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    # Most event objects have aliases for API methods that can be called in events' context
    # For example if you want to answer to incoming message you can use `message.answer(...)` alias
    # and the target chat will be passed to :ref:`aiogram.methods.send_message.SendMessage`
    # method automatically or call API method directly via
    # Bot instance: `bot.send_message(chat_id=message.chat.id, ...)`
    logger.debug(
        "Start command received", message=message.model_dump(exclude_none=True)
    )

    assert message.from_user
    assert message.chat

    await message.answer(
        f"Hi {html.bold(message.from_user.first_name)}! Our chat id is {html.code(str(message.chat.id))}.",
        parse_mode=ParseMode.HTML,
    )


@dp.message()
@logfire.instrument(new_trace=True)
async def on_unknown_message(message: Message) -> None:
    logger.debug(
        "Unknown message received", message=message.model_dump(exclude_none=True)
    )
    await message.answer("Sorry, I don't know what to say.")


@logfire.instrument(new_trace=True)
async def run():
    # Initialize Bot instance
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])

    logger.debug("Bot started")

    # And the run events dispatching
    await dp.start_polling(bot)


@logfire.instrument()
def startup():
    asyncio.create_task(run())
