import logging

from pydantic_ai import Agent

from src.telegram.bot.messages.messages_constants import RESPONSE_AGENT_PROMPT
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


async def run_response_agent(
    query: str,
    deps: ResponseDependencies,
) -> str:
    logger.debug("Running decision agent")

    response = await response_agent.run(query, deps=deps)  # type: ignore
    return response.output
