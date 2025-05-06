import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from aiohttp import ClientTimeout
from aiohttp.client_exceptions import ContentTypeError

from src.shared.exceptions import HTTPError

logger = logging.getLogger("athena.shared.http")


class AsyncHttpClient:
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        async with aiohttp.ClientSession() as session:
            yield session

    async def request(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> dict[str, Any] | str:
        async with self.session() as session:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                timeout=ClientTimeout(total=20),
            ) as response:
                try:
                    return await response.json()
                except ContentTypeError:
                    return await response.text()
                except aiohttp.ClientError as e:
                    raise HTTPError(response.status, await response.text()) from e
                except Exception as e:
                    raise HTTPError(response.status, await response.text()) from e
