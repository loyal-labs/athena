from typing import Any

from src.shared.http import AsyncHttpClient


class PostsModel:
    @staticmethod
    async def get_posts(
        http_client: AsyncHttpClient, url: str, offset_date: str, limit: int
    ) -> dict[str, Any]:
        """
        Get posts from a group
        """
        params = {
            "offset_date": offset_date,
            "limit": limit,
        }
        response = await http_client.request(url, params=params)
        return response
