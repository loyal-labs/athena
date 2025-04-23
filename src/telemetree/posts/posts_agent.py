import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from pydantic_ai import Agent, RunContext
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from src.telemetree.posts.posts_constants import (
    CHECK_QUERY_AGENT_PROMPT,
    CLEAN_UP_AGENT_PROMPT,
    POSTS_AGENT_PROMPT,
)
from src.telemetree.posts.posts_schemas import ChannelPost, Output

if TYPE_CHECKING:
    from src.telemetree.posts.posts_service import PostsService

logger = logging.getLogger("athena.telemetree.posts")


@dataclass
class PostsState:
    query: str
    username: str
    limit: int
    offset_days: int
    service: "PostsService"


#
# -- Agents --
#

posts_agent = Agent(
    "google-vertex:gemini-2.5-flash-preview-04-17",
    output_type=Output,
    system_prompt=POSTS_AGENT_PROMPT,
)

check_query_agent = Agent(
    "google-vertex:gemini-2.5-flash-preview-04-17",
    output_type=bool,
    system_prompt=CHECK_QUERY_AGENT_PROMPT,
)

clean_up_agent = Agent(
    "google-vertex:gemini-2.5-flash-preview-04-17",
    output_type=Output,
    system_prompt=CLEAN_UP_AGENT_PROMPT,
)


#
# -- Tools--
#
@posts_agent.tool  # type: ignore
async def get_posts(ctx: RunContext[PostsState]) -> list[ChannelPost]:
    try:
        logger.debug("Fetching posts")
        service = ctx.deps.service
        posts = await service.get_posts(
            ctx.deps.username, ctx.deps.limit, ctx.deps.offset_days
        )
        return posts
    except Exception as e:
        logger.exception("Error getting posts from %s", ctx.deps.username)
        raise e


#
# -- Graph --
#
@dataclass
class CheckQuery(BaseNode[PostsState]):
    async def run(
        self, ctx: GraphRunContext[PostsState]
    ) -> Union["CleanUpQuery", "GetPosts"]:
        query = ctx.state.query
        logger.debug("Checking query")
        is_safe_run = await check_query_agent.run(query)
        is_safe = is_safe_run.output
        logger.debug("Query is safe: %s", is_safe)

        if is_safe:
            logger.debug("Query is safe, getting posts")
            return GetPosts()
        else:
            logger.debug("Query is not safe, cleaning up")
            return CleanUpQuery()


@dataclass
class CleanUpQuery(BaseNode[PostsState]):
    async def run(self, ctx: GraphRunContext[PostsState]) -> "GetPosts":
        query = ctx.state.query
        logger.debug("Cleaning up query")
        clean_up_run = await clean_up_agent.run(query)
        ctx.state.query = clean_up_run.output.response
        logger.debug("Query cleaned up: %s", ctx.state.query)
        return GetPosts()


@dataclass
class GetPosts(BaseNode[PostsState, None, Output]):
    async def run(self, ctx: GraphRunContext[PostsState]) -> End[Output]:
        query = ctx.state.query
        logger.debug("Getting posts, query: %s", query)

        # TODO: check if we need this
        deps = PostsState(
            query=query,
            username=ctx.state.username,
            limit=ctx.state.limit,
            offset_days=ctx.state.offset_days,
            service=ctx.state.service,
        )

        results = await posts_agent.run(query, deps=deps)  # type: ignore

        output = results.output
        logger.debug("Response: %s", output)
        return End(output)


async def run_posts_graph(
    query: str,
    posts_service: "PostsService",
    username: str,
    limit: int,
    offset_days: int,
) -> Output:
    state = PostsState(
        query=query,
        username=username,
        limit=limit,
        offset_days=offset_days,
        service=posts_service,
    )
    posts_query_graph = Graph(nodes=[CheckQuery, CleanUpQuery, GetPosts])
    logger.debug("Running posts query graph")

    results = await posts_query_graph.run(start_node=CheckQuery(), state=state)
    logger.debug("Posts query graph results: %s", results)
    return results.output


async def is_safe_query(query: str) -> Output:
    response = await clean_up_agent.run(f"Please clean up the following query: {query}")
    return response.output
