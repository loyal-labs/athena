import logging
from typing import Literal

from pydantic_ai import Agent, RunContext

from src.shared.event_registry import TelemetreeTopics
from src.telegram.bot.messages.messages_constants import (
    DECISION_AGENT_PROMPT,
    RESPONSE_AGENT_PROMPT,
)
from src.telegram.bot.messages.messages_schemas import ResponseDependencies

logger = logging.getLogger("athena.telegram.messages.agent")


#
# -- Agents --
#

response_agent = Agent(
    "google-vertex:gemini-2.5-flash-preview-04-17",
    output_type=str,
    system_prompt=RESPONSE_AGENT_PROMPT,
)

decision_agent = Agent(
    "google-vertex:gemini-2.5-flash-preview-04-17",
    output_type=str,
    system_prompt=DECISION_AGENT_PROMPT,
)


#
# -- Tools --
#
@decision_agent.tool  # type: ignore
async def delegate_to_news_agent(
    ctx: RunContext[ResponseDependencies],
    query: str,
    language: Literal["en", "ru"],
) -> str:
    """
    Hands off the query to the agent querying the news.

    Call the tool when you need to get the news.

    Parameters:
        query: str - The query to delegate to the news agent.

    Returns:
        str - The response from the news agent.
    """
    logger.debug("Delegating to news agent")

    event_bus = ctx.deps.event_bus
    message = ctx.deps.message
    if language == "en":
        await message.reply_text(  # type: ignore
            "<i>Fetching news from Telemetree... please wait a moment.</i>"
        )
    else:
        await message.reply_text(  # type: ignore
            "<i>Отправляю запрос в Telemetree... займет минутку!</i>"
        )

    response = await event_bus.request(
        TelemetreeTopics.GET_CHANNEL_POSTS_AGENT,
        query=query,
    )

    return response


@decision_agent.tool  # type: ignore
async def delegate_to_chat_agent(
    ctx: RunContext[ResponseDependencies],
    query: str,
) -> str:
    """
    Hands off the query to the agent chatting with the user.

    Call the tool when you need to chat with the user.

    Parameters:
        query: str - The query to delegate to the chat agent.
    """
    logger.debug("Delegating to chat agent")
    chat_history = ctx.deps.last_messages
    message_history = f"**Message history**:\n\n{chat_history}"
    query = f"{message_history}\n\n**Query**: {query}"

    result = await response_agent.run(query, deps=ctx.deps)  # type: ignore
    return result.output


#
# -- Functions --
#


async def run_decision_agent(
    query: str,
    deps: ResponseDependencies,
) -> str:
    logger.debug("Running decision agent")

    response = await decision_agent.run(query, deps=deps)  # type: ignore
    return response.output
