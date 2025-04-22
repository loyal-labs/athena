from abc import ABC, abstractmethod

from pydantic_ai import Agent

from src.shared.base_llm import ProviderBase


class BaseAgent(ABC):
    @property
    @abstractmethod
    def agent(self) -> Agent:
        pass

    @abstractmethod
    def create_agent(self, model_object: ProviderBase) -> Agent:
        pass
