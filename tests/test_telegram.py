import os

import pytest
from aiogram.enums import ParseMode

pytestmark = pytest.mark.skipif(
    not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"),
    reason="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,format",
    [
        ("HTML test: plain text smoke test.", ParseMode.HTML),
        (
            "HTML test with add-on features: <b>bold</b>, <i>italic</i>, "
            "<u>underline</u>, <s>strike</s>, <code>code</code>, "
            'and <a href="https://example.com">link</a>.\n'
            "<tg-spoiler>classified test payload</tg-spoiler>\n"
            "Image: https://picsum.photos/seed/agent-penny-telegram-html/640/360",
            ParseMode.HTML,
        ),
        (
            "MarkdownV2 test: plain text smoke test\\.",
            ParseMode.MARKDOWN_V2,
        ),
        (
            "MarkdownV2 test with add\\-on features: *bold*, _italic_, "
            "__underline__, ~strike~, `code`, and "
            "[link](https://example.com)\\.\n"
            "||classified test payload||\n"
            "Image: https://picsum\\.photos/seed/agent\\-penny\\-telegram\\-markdown/640/360",
            ParseMode.MARKDOWN_V2,
        ),
    ],
)
async def test_telegram_send(text: str, format: ParseMode):
    from agent_penny.capabilities.telegram import _bot, telegram_send

    try:
        await telegram_send(os.environ["TELEGRAM_CHAT_ID"], text, format)
    finally:
        await _bot().session.close()
        _bot.cache_clear()
