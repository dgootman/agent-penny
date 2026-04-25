import os
from dataclasses import dataclass
from functools import cache
from typing import Any, override

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
from pydantic_ai import AgentToolset, FunctionToolset, ModelRetry
from pydantic_ai.capabilities import AbstractCapability

toolset = FunctionToolset()


@cache
def _bot() -> Bot:
    return Bot(os.environ["TELEGRAM_BOT_TOKEN"])


@toolset.tool_plain
async def telegram_send(
    chat_id: str, text: str, format: ParseMode = ParseMode.HTML
) -> dict[str, Any]:
    """
    Send a message on Telegram

    Args:
        chat_id: The chat id to send the message to.
        text: The message text to send. The format is specified in the format field.
        format: The Telegram format of the text. Supports HTML (default) or MarkdownV2.

    Returns:
        The Telegram message that was sent.

    Raises:
        ModelRetry: There was a problem with the request, such as invalid syntax for HTML or MarkdownV2.
    """

    bot = _bot()

    try:
        message = await bot.send_message(chat_id, text, parse_mode=format)
    except TelegramBadRequest as e:
        raise ModelRetry(e.message) from e

    message_dict = bot.session.prepare_value(message, bot, {}, _dumps_json=False)
    logger.debug("Message sent", message=message_dict)

    return message_dict


@dataclass
class TelegramCapability(AbstractCapability[Any]):
    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return toolset
