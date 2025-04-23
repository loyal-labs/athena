import logging
from datetime import datetime, timedelta
from typing import cast

from src.shared.base import BaseService
from src.shared.event_bus import EventBus
from src.shared.event_registry import TelemetreeTopics
from src.shared.events import Event
from src.shared.http import AsyncHttpClient
from src.telemetree.posts.posts_agent import run_posts_graph
from src.telemetree.posts.posts_constants import TG_NEWS_OUTLET
from src.telemetree.posts.posts_model import PostsModel
from src.telemetree.posts.posts_schemas import (
    ChannelPost,
    GetChannelPostsPayload,
    NewsPostsInputPayload,
    Output,
)
from src.telemetree.shared.telemetree_config import TelemetreeConfig
from src.telemetree.shared.telemetree_endpoints import (
    DATALAKE_ENDPOINT,
    GET_POSTS_ENDPOINT,
)

logger = logging.getLogger("athena.telemetree.posts")


class PostsService(BaseService):
    def __init__(self, config: TelemetreeConfig):
        self.config = config
        self.http_client = AsyncHttpClient()

    def __calculate_offset_date(self, offset_days: int) -> str:
        """
        Calculate the offset date

        Args:
            offset_days (int): The number of days to offset the date by (default is 30)

        Returns:
            str: The offset date in the format YYYY-MM-DDTHH:MM:SS
        """
        today = datetime.now()
        offset_date = today - timedelta(days=offset_days)
        return offset_date.strftime("%Y-%m-%dT%H:%M:%S")

    @EventBus.subscribe(TelemetreeTopics.GET_CHANNEL_POSTS)
    async def on_get_posts(self, event: Event) -> list[ChannelPost]:
        payload = cast(
            GetChannelPostsPayload, event.extract_payload(event, GetChannelPostsPayload)
        )
        username = payload.group_username
        limit = payload.limit
        offset_days = payload.offset_days

        posts = await self.get_posts(username, limit, offset_days)
        return posts

    async def get_posts(
        self, group_username: str, limit: int, offset_days: int
    ) -> list[ChannelPost]:
        """
        Get posts from a group
        """
        url = f"{DATALAKE_ENDPOINT}{GET_POSTS_ENDPOINT.format(username=group_username)}"
        offset_date = self.__calculate_offset_date(offset_days)

        response = await PostsModel.get_posts(self.http_client, url, offset_date, limit)
        try:
            assert response
            assert response["posts"]
        except AssertionError as e:
            logger.exception("Error getting posts from %s", group_username)
            raise e
        except Exception as e:
            logger.exception("Error getting posts from %s", group_username)
            raise e

        posts = [
            ChannelPost.from_telemetree_response(post) for post in response["posts"]
        ]

        return posts

    @EventBus.subscribe(TelemetreeTopics.GET_CHANNEL_POSTS_AGENT)
    async def on_get_posts_agent(self, event: Event) -> Output:
        logger.debug("Fetching posts from %s", TG_NEWS_OUTLET)
        payload = cast(
            NewsPostsInputPayload,
            event.extract_payload(event, NewsPostsInputPayload),
        )
        query = payload.query
        username = TG_NEWS_OUTLET
        limit = 100
        offset_days = 30

        return await self.fetch_posts(query, username, limit, offset_days)

    async def fetch_posts(
        self, query: str, username: str, limit: int, offset_days: int
    ) -> Output:
        try:
            logger.debug("Fetching posts from %s", username)
            return await run_posts_graph(query, self, username, limit, offset_days)
        except Exception as e:
            logger.exception("Error fetching posts")
            raise e
