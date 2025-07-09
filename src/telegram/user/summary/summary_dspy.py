"""DSPy pipeline for Telegram message summarization and topic extraction."""

from datetime import datetime
from typing import Any, cast

import dspy
import orjson

from src.shared.base_llm import LLMFactory
from src.telegram.user.summary.summary_schemas import TelegramMessage


class TopicSummary(dspy.Signature):
    """Extract topics and key points from messages in a single pass."""

    messages: str = dspy.InputField(  # type: ignore
        desc="JSON array of messages with author, timestamp, and content"
    )

    topics: str = dspy.OutputField(  # type: ignore
        desc="JSON array of distinct topics discussed. Group related messages into separate topics. Each topic must have: title (2-4 words), key_points (array of max 3 objects with 'username' and 'point' fields), and message_indices (array of message indexes belonging to this topic). Analyze the conversation flow and create multiple topics when the discussion shifts (3 max). Each point should be a concise action or statement."
    )


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
                "total_participants": 0,
                "topics": [],
            }

        # Sort messages by timestamp
        messages = sorted(messages, key=lambda m: m.timestamp)

        # Prepare messages for LLM (simplified format)
        messages_data: list[dict[str, Any]] = []
        for i, msg in enumerate(messages):
            author = msg.first_name or msg.username or "Unknown"
            messages_data.append(
                {
                    "idx": i,
                    "author": author,
                    "time": msg.timestamp.strftime("%H:%M"),
                    "text": msg.message[:200],  # Truncate long messages
                }
            )

        # Single LLM call to extract topics and summaries
        try:
            result = self.extract_topics(messages=orjson.dumps(messages_data))  # type: ignore
            assert isinstance(result, TopicSummary), "Result is not a TopicSummary"
            topics_data = orjson.loads(result.topics)
        except Exception as e:
            print(f"Error extracting topics: {e}")
            # Fallback: single topic with all messages
            topics_data = [
                {
                    "title": "General Discussion",
                    "key_points": [
                        {"username": "Unknown", "point": "Various messages exchanged"}
                    ],
                    "message_indices": list(range(len(messages))),
                }
            ]

        # Format output
        topics: list[dict[str, Any]] = []
        for topic in topics_data:
            # Get messages for this topic
            topic_messages: list[TelegramMessage] = [
                messages[i]  # type: ignore
                for i in topic.get("message_indices", [])  # type: ignore
            ]
            if not topic_messages:
                continue

            # Extract participants for this topic
            participants = list(
                {m.first_name or m.username or "Unknown" for m in topic_messages}
            )

            topics.append(
                {
                    "title": topic.get("title", topic.get("topic_name", "Discussion")),
                    "key_points": topic.get(
                        "key_points", topic.get("summary_points", [])
                    )[:3],  # Max 3 points
                    "participants": participants,
                    "message_count": len(topic_messages),
                    "start_time": topic_messages[0].timestamp.strftime("%H:%M"),
                    "end_time": topic_messages[-1].timestamp.strftime("%H:%M"),
                }
            )

        return {
            "chat_name": chat_name,
            "chat_type": chat_type,
            "time_period": self._format_time_period(
                messages[0].timestamp, messages[-1].timestamp
            ),
            "total_participants": len(
                {m.first_name or m.username or "Unknown" for m in messages}
            ),
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

    lm = dspy.LM(
        "gemini/gemini-2.5-flash-lite-preview-06-17",
        api_key=gemini_api_key,
        max_tokens=max_tokens,
    )
    dspy.settings.configure(lm=lm)  # type: ignore

    # Create and run the pipeline
    pipeline = TelegramSummaryPipeline()
    summary = pipeline(messages, chat_name, chat_type)  # type: ignore

    return cast(dict[str, Any], summary)
