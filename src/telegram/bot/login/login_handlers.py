import logging

import orjson
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import MessageServiceType
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message, WebAppData

from src.shared.database import DatabaseFactory
from src.telegram.user.login.login_schemas import LoginSession
from src.telegram.user.onboarding.onboarding_service import OnboardingService
from telegram.user.telegram_session_manager import UserSessionFactory

logger = logging.getLogger("athena.telegram.login.handlers")


class LoginHandlers:
    """
    Login handlers class
    """

    def _parse_web_app_data(self, web_app_data: WebAppData) -> tuple[int, bytes]:
        assert web_app_data is not None, "Web app data is None"
        assert web_app_data.data is not None, "Web app data is None"

        web_app_data_str = web_app_data.data
        try:
            data_dict = orjson.loads(web_app_data_str)
        except orjson.JSONDecodeError as e:
            logger.error("Failed to parse web_app_data: %s", web_app_data_str)
            raise ValueError(f"Failed to parse web_app_data: {web_app_data_str}") from e
        except Exception as e:
            logger.error("Failed to parse web_app_data: %s", e)
            raise ValueError(f"Failed to parse web_app_data: {e}") from e

        dc_id = data_dict.get("dc_id")
        auth_key = data_dict.get("auth_key")
        assert dc_id
        assert auth_key

        return dc_id, auth_key

    async def shared_data_filter(self, _, client: Client, message: Message) -> bool:
        if (
            message.service is not None
            and message.service == MessageServiceType.WEB_APP_DATA
        ):
            return True
        return False

    async def login_message(self, client: Client, message: Message) -> None:
        assert message.web_app_data is not None, "Web app data is None"
        assert message.from_user is not None, "From user is None"
        assert message.from_user.id is not None, "From user ID is None"

        dc_id, auth_key = self._parse_web_app_data(message.web_app_data)

        user_session_manager = await UserSessionFactory.get_instance()
        database = await DatabaseFactory.get_instance()

        async with database.session() as db_session:
            await user_session_manager.create_new_session(
                owner_id=message.from_user.id,
                dc_id=dc_id,
                auth_key=auth_key,
                db_session=db_session,
            )

            # Check if first-time user and run onboarding
            login_sessions = await LoginSession.get_by_owner(
                message.from_user.id, db_session
            )
            if login_sessions and not login_sessions[0].is_onboarded:
                onboarding = OnboardingService()
                await onboarding.run_onboarding_pipeline(message.from_user.id)

    @property
    def login_handlers(self) -> list[Handler]:
        shared_data_filter = filters.create(self.shared_data_filter)  # type: ignore

        return [
            MessageHandler(self.login_message, filters.incoming & shared_data_filter),
        ]
