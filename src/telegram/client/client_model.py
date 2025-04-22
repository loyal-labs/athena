import logging

from pyrogram.client import Client
from pyrogram.enums import ParseMode
from pyrogram.types import Message

logger = logging.getLogger("athena.telegram.client")


class Telegram:
    async def send_poll(
        self,
        client: Client,
        chat_id: int | str,
        question: str,
        options: list[str],
        is_anonymous: bool = True,
        explanation: str | None = None,
    ) -> Message:
        try:
            assert client
            assert isinstance(chat_id, int) or isinstance(chat_id, str)
            assert isinstance(question, str)
            assert len(question) < 256
            assert isinstance(options, list)
            assert len(options) > 1
            assert all(isinstance(option, str) for option in options)
            for option in options:
                assert len(option) < 100
            assert isinstance(is_anonymous, bool)
            assert isinstance(explanation, str | None)
            assert explanation is None or len(explanation) < 200
        except AssertionError as e:
            logger.error("Error sending poll: %s", e)
            raise e

        try:
            message = await client.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=is_anonymous,
                explanation=explanation,
                question_parse_mode=ParseMode.MARKDOWN,
            )
            logger.info("Poll sent to chat %s", chat_id)
            return message
        except Exception as e:
            logger.error("Error sending poll: %s", e)
            raise e


telegram = Telegram()
