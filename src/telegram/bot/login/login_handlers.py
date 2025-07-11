import logging
from typing import cast

import orjson
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import MessageServiceType
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message, WebAppData

from src.shared.database import DatabaseFactory
from src.telegram.user.onboarding.onboarding_schemas import OnboardingSchema
from src.telegram.user.onboarding.onboarding_service import OnboardingService
from src.telegram.user.telegram_session_manager import UserSessionFactory

logger = logging.getLogger("athena.telegram.login.handlers")


class LoginHandlers:
    """
    Login handlers class
    """

    DC_ID_NAME = "dcId"
    AUTH_KEY_NAME = "authKeyHex"

    @staticmethod
    def _parse_web_app_data(web_app_data: WebAppData) -> tuple[int, bytes]:
        assert web_app_data is not None, "Web app data is None"
        assert web_app_data.data is not None, "Web app data is None"

        web_app_data_service_msg_content = web_app_data.data
        try:
            web_app_data_str = cast(str, web_app_data_service_msg_content.data)  # type: ignore
        except AttributeError:
            web_app_data_str = cast(str, web_app_data_service_msg_content)  # type: ignore
        except Exception as e:
            logger.error("Failed to parse web_app_data: %s", e)
            raise ValueError(f"Failed to parse web_app_data: {e}") from e

        try:
            text_dict = orjson.loads(web_app_data_str.strip().encode("utf-8"))
        except orjson.JSONDecodeError as e:
            logger.error("Failed to parse web_app_data: %s", web_app_data_str)
            raise ValueError(f"Failed to parse web_app_data: {web_app_data_str}") from e
        except Exception as e:
            logger.error("Failed to parse web_app_data: %s", e)
            raise ValueError(f"Failed to parse web_app_data: {e}") from e

        dc_id = text_dict.get(LoginHandlers.DC_ID_NAME)
        auth_key = text_dict.get(LoginHandlers.AUTH_KEY_NAME)

        assert dc_id, "DC ID is None"
        assert auth_key, "Auth key is None"

        try:
            dc_id = int(dc_id)
            auth_key = bytes.fromhex(auth_key)
        except ValueError as e:
            logger.error("Failed to parse web_app_data: %s", e)
            raise ValueError(f"Failed to parse web_app_data: {e}") from e

        return dc_id, auth_key

    @staticmethod
    async def shared_data_filter(_, client: Client, message: Message) -> bool:
        if (
            message.service is not None
            and message.service == MessageServiceType.WEB_APP_DATA
        ):
            return True
        return False

    @staticmethod
    async def login_message(client: Client, message: Message) -> None:
        assert message.web_app_data is not None, "Web app data is None"
        assert message.from_user is not None, "From user is None"
        assert message.from_user.id is not None, "From user ID is None"

        dc_id, auth_key = LoginHandlers._parse_web_app_data(message.web_app_data)

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
            onboarding_status = await OnboardingSchema.get(
                message.from_user.id, db_session
            )
            if onboarding_status and not onboarding_status.is_onboarded:
                onboarding = OnboardingService()
                await onboarding.run_onboarding_pipeline(message.from_user.id)

    @property
    def login_handlers(self) -> list[Handler]:
        shared_data_filter = filters.create(LoginHandlers.shared_data_filter)  # type: ignore

        return [
            MessageHandler(
                LoginHandlers.login_message, filters.incoming & shared_data_filter
            ),
        ]
