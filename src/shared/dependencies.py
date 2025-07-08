import base64
import hashlib
import hmac
import time
from typing import Annotated

import orjson
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from src.shared.database import Database, DatabaseFactory
from src.telegram.bot.client.telegram_bot import TelegramBot, TelegramBotFactory

#
# -- Schemas --
#
security = HTTPBearer()


class TelegramLoginParams(BaseModel):
    id: str = Field(..., description="Telegram user ID")
    first_name: str = Field(..., description="Telegram user first name")
    last_name: str | None = Field(default=None, description="Telegram user last name")
    username: str | None = Field(default=None, description="Telegram user username")
    photo_url: str | None = Field(default=None, description="Telegram user photo URL")
    auth_date: str = Field(..., description="Telegram auth date")
    hash: str = Field(..., description="Telegram auth hash")


#
# -- Dependency Injections --
#
async def get_telegram_params_from_auth_header(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> TelegramLoginParams:
    """Extract Telegram login params from Authorization header using FastAPI security"""
    try:
        if credentials.scheme != "Bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication scheme",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Decode base64 encoded JSON
        decoded_bytes = base64.b64decode(credentials.credentials)
        data = orjson.loads(decoded_bytes)

        return TelegramLoginParams(**data)

    except (orjson.JSONDecodeError, KeyError, ValueError) as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization data",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_database() -> Database:
    return await DatabaseFactory.get_instance()


async def get_telegram_bot() -> TelegramBot:
    return await TelegramBotFactory.get_instance()


async def verify_telegram_auth(
    params: Annotated[
        TelegramLoginParams, Depends(get_telegram_params_from_auth_header)
    ],
    bot: Annotated[TelegramBot, Depends(get_telegram_bot)],
) -> TelegramLoginParams:
    """
    Verify that the request is coming from Telegram.
    """
    bot_token = bot.api_token
    assert bot_token is not None, "Bot token is not set"

    hmac_result = hmac_check(params, bot)
    auth_date_result = auth_date_check(params)

    try:
        assert hmac_result, "HMAC check failed"
        assert auth_date_result, "Auth date check failed"
    except AssertionError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    return params


#
# -- Helper Functions --
#

AUTH_DATA_MAX_AGE = 60 * 60 * 24 * 30  # 30 days # TODO: implement JWT signing later on


def hmac_check(params: TelegramLoginParams, bot: TelegramBot) -> bool:
    bot_token = bot.api_token
    assert bot_token is not None, "Bot token is not set"

    check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.model_dump().items()) if k != "hash"
    )
    secret = hashlib.sha256(bot_token.encode()).digest()
    hmac_result = (
        hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        == params.hash
    )
    return hmac_result


def auth_date_check(params: TelegramLoginParams) -> bool:
    auth_date = params.auth_date
    assert auth_date is not None, "Auth date is not set"
    auth_date_int = int(auth_date)
    current_time = int(time.time())
    return abs(auth_date_int - current_time) <= AUTH_DATA_MAX_AGE
