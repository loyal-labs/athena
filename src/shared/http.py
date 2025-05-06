import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from aiohttp import ClientTimeout

from src.shared.exceptions import HTTPError

logger = logging.getLogger("athena.shared.http")


class AsyncHttpClient:
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        async with aiohttp.ClientSession() as session:
            yield session

    async def get_request(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self.session() as session:
            async with session.get(
                url, headers=headers, params=params, timeout=ClientTimeout(total=20)
            ) as response:
                try:
                    return await response.json()
                except aiohttp.ClientError as e:
                    raise HTTPError(response.status, await response.text()) from e
