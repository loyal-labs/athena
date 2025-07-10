"""DSPy pipeline for Telegram message summarization and topic extraction."""

import logging
from datetime import datetime
from typing import Any, cast

import dspy
import orjson
from dspy.primitives.prediction import Prediction
from pydantic import BaseModel, Field, RootModel

from src.shared.base_llm import LLMFactory
from src.telegram.user.summary.summary_schemas import TelegramMessage


# Pydantic schemas for LLM raw JSON response validation
class LLMKeyPoint(BaseModel):
    """Key point structure in LLM response."""

    username: str = Field(
        ..., description="Username of the participant who made this point"
    )
    point: str = Field(
        ..., description="Concise description of the key point or action"
    )


class LLMTopicResponse(BaseModel):
    """Single topic structure in LLM JSON response."""

    title: str = Field(..., description="2-4 word title describing the topic")
    key_points: list[LLMKeyPoint] = Field(
        ...,
        max_length=3,
        description="Array of max 3 objects with 'username' and 'point' fields",
    )


class LLMTopicsResponse(RootModel[list[LLMTopicResponse]]):
    """Root validation schema for LLM topics JSON response."""

    root: list[LLMTopicResponse] = Field(
        ...,
        max_length=3,
        description="JSON array of distinct topics discussed (max 3)",
    )


class TopicSummary(dspy.Signature):
    """Extract topics and key points from messages in a single pass."""

    messages: str = dspy.InputField(  # type: ignore
        desc="Text of messages with author, timestamp, and content"
    )

    topics: LLMTopicsResponse = dspy.OutputField()  # type: ignore


class TelegramSummaryPipeline(dspy.Module):
    """Optimized DSPy pipeline for summarizing Telegram conversations."""

    def __init__(self):
        super().__init__()  # type: ignore
        self.extract_topics = dspy.ChainOfThought(TopicSummary)

    def forward(
        self, messages: list[TelegramMessage], chat_name: str, chat_type: str
    ) -> dict[str, Any]:
        """
        Process messages and generate structured summary with minimal LLM calls.

        Args:
            messages: List of ChatMessage objects to analyze
            chat_name: Name of the chat/channel
            chat_type: Type of chat (private, group, channel)

        Returns:
            Dictionary with chat metadata and topic summaries
        """
        if not messages:
            return {
                "chat_name": chat_name,
                "chat_type": chat_type,
                "time_period": "No messages",
                "max_message_id": 0,
                "total_participants": 0,
                "topics": [],
            }

        # Single LLM call to extract topics and summaries
        try:
            text = TelegramMessage.messages_to_text(messages)
            result = self.extract_topics(messages=text)  # type: ignore
            assert isinstance(result, Prediction), "Result is not a Prediction"
        except Exception as e:
            logging.error(f"Error extracting topics: {e}")
            raise e from e

        try:
            assert isinstance(result.topics, LLMTopicsResponse), (  # type: ignore
                "Result topics are not a string"
            )
            topics_data = result.topics.model_dump()
        except orjson.JSONDecodeError:
            topics_data = result.topics.replace("```json", "").replace("```", "")  # type: ignore
            topics_data = orjson.loads(topics_data)  # type: ignore
        except Exception as e:
            logging.error(f"Error parsing topics: {e}")
            raise e from e

        # Format output
        topics: list[dict[str, Any]] = []
        for topic in topics_data:
            # Extract participants for this topic
            participants = list({m.title or m.username or "Unknown" for m in messages})

            topics.append(
                {
                    "title": topic.get("title", topic.get("topic_name", "Discussion")),
                    "key_points": topic.get(
                        "key_points", topic.get("summary_points", [])
                    )[:3],  # Max 3 points
                    "participants": participants,
                    "message_count": len(messages),
                    "start_time": messages[0].timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": messages[-1].timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        max_message_id = max(m.message_id for m in messages)

        return {
            "chat_name": chat_name,
            "chat_type": chat_type,
            "time_period": "No messages",
            "max_message_id": max_message_id,
            "total_participants": 0,
            "topics": topics,
        }

    def _format_time_period(self, start: datetime, end: datetime) -> str:
        """Format the time period covered by messages."""
        duration = end - start

        if duration.days > 1:
            return f"{duration.days} days"
        elif duration.days == 1:
            return "1 day"
        elif duration.seconds > 3600:
            hours = duration.seconds // 3600
            return f"{hours} hours"
        else:
            minutes = duration.seconds // 60
            return f"{minutes} minutes"


async def summarize_chat_messages(
    messages: list[TelegramMessage],
    chat_name: str,
    chat_type: str,
) -> dict[str, Any]:
    """
    Summarize chat messages using optimized DSPy pipeline.

    Args:
        messages: List of ChatMessage objects
        chat_name: Name of the chat
        chat_type: Type of chat (PRIVATE, GROUP, CHANNEL)
        model_name: Model to use for summarization

    Returns:
        Dictionary with chat summary including topics and key points
    """
    # Configure DSPy with the model
    vertex_llm = await LLMFactory.get_instance()
    gemini_api_key = vertex_llm.gemini_api_key
    max_tokens = 8000
    temperature = 0.8

    lm = dspy.LM(
        "gemini/gemini-2.5-flash-lite-preview-06-17",
        api_key=gemini_api_key,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    dspy.settings.configure(lm=lm)  # type: ignore

    # Create and run the pipeline
    pipeline = TelegramSummaryPipeline()
    summary = pipeline(messages, chat_name, chat_type)  # type: ignore

    return cast(dict[str, Any], summary)
