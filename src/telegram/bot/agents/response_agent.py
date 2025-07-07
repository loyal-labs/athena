"""
This module contains the ElementsAgent class which is responsible for LLM-driven interactions
"""

import logging

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.shared.base import BaseService
from src.shared.base_llm import VertexLLM
from src.telegram.bot.agents.prompts import RESPONSE_SYSTEM_PROMPT

logger = logging.getLogger("athena.telegram.response")


class GroupResponseAgent(BaseService):
    def __init__(self, provider: VertexLLM):
        super().__init__()
        self.provider = provider

        self.agent_object = Agent(
            name="Group Response Agent",
            model=self.provider.model,
            system_prompt=RESPONSE_SYSTEM_PROMPT,
            model_settings=ModelSettings(
                temperature=1,
                max_tokens=300,
            ),
            retries=3,
        )
