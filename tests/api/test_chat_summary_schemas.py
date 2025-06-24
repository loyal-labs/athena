import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.api.summary.summary_schemas import (
    ChatSummary,
    ChatSummaryPoint,
    ChatSummaryTopic,
    ChatTypes,
)


@pytest.fixture
def mock_chat_summaries():
    """Load mock chat summary data from JSON fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "chat_summary_mocks.json"
    with open(fixture_path) as f:
        return json.load(f)


class TestChatSummaryPoint:
    """Test ChatSummaryPoint schema validation."""

    def test_valid_chat_summary_point(self):
        """Test creating a valid ChatSummaryPoint."""
        point_data = {
            "name": "John Doe",
            "profile_picture": "data:image/png;base64,abc123",
            "summary": "Made an important point about the project",
        }
        point = ChatSummaryPoint(**point_data)

        assert point.name == "John Doe"
        assert point.profile_picture == "data:image/png;base64,abc123"
        assert point.summary == "Made an important point about the project"

    def test_missing_required_fields(self):
        """Test validation error when required fields are missing."""
        with pytest.raises(ValidationError):
            ChatSummaryPoint(
                name="John Doe"
            )  # Missing profile_picture and summary # type: ignore


class TestChatSummaryTopic:
    """Test ChatSummaryTopic schema validation."""

    def test_valid_chat_summary_topic(self):
        """Test creating a valid ChatSummaryTopic."""
        topic_data = {
            "topic": "Project Discussion",
            "date": "2024-06-24T14:30:00",
            "points": [
                {
                    "name": "Alice",
                    "profile_picture": "data:image/png;base64,alice123",
                    "summary": "Suggested new approach",
                },
                {
                    "name": "Bob",
                    "profile_picture": "data:image/png;base64,bob123",
                    "summary": "Agreed with Alice's proposal",
                },
            ],
        }
        topic = ChatSummaryTopic(**topic_data)  # type: ignore

        assert topic.topic == "Project Discussion"
        assert isinstance(topic.date, datetime)
        assert len(topic.points) == 2
        assert all(isinstance(point, ChatSummaryPoint) for point in topic.points)

    def test_datetime_parsing(self):
        """Test that datetime strings are properly parsed."""
        topic_data: dict[str, str | list[dict[str, str]]] = {
            "topic": "Test Topic",
            "date": "2024-06-24T14:30:00",
            "points": [],
        }
        topic = ChatSummaryTopic(**topic_data)  # type: ignore

        assert topic.date == datetime(2024, 6, 24, 14, 30, 0)


class TestChatSummary:
    """Test ChatSummary schema validation."""

    def test_valid_chat_summary(
        self, mock_chat_summaries: list[dict[str, str | list[dict[str, str]]]]
    ):
        """Test creating valid ChatSummary objects from mock data."""
        for chat_data in mock_chat_summaries:
            chat_summary = ChatSummary(**chat_data)  # type: ignore

            # Validate basic structure
            assert isinstance(chat_summary.name, str)
            assert chat_summary.profile_picture.startswith("https://")
            assert isinstance(chat_summary.topics, list)
            assert len(chat_summary.topics) > 0
            assert chat_summary.chat_type in ChatTypes

            # Validate topics
            for topic in chat_summary.topics:
                assert isinstance(topic, ChatSummaryTopic)
                assert isinstance(topic.topic, str)
                assert isinstance(topic.date, datetime)
                assert isinstance(topic.points, list)
                assert len(topic.points) > 0

                # Validate points
                for point in topic.points:
                    assert isinstance(point, ChatSummaryPoint)
                    assert isinstance(point.name, str)
                    assert point.profile_picture.startswith("https://")
                    assert isinstance(point.summary, str)

    def test_startup_chat_specific_data(
        self, mock_chat_summaries: list[dict[str, str | list[dict[str, str]]]]
    ):
        """Test specific data from the startup chat mock."""
        startup_chat = ChatSummary(**mock_chat_summaries[0])  # type: ignore

        assert startup_chat.name == "StartupHub Solana"
        assert len(startup_chat.topics) == 2
        assert startup_chat.chat_type == ChatTypes.GROUP

        # Test first topic
        first_topic = startup_chat.topics[0]
        assert first_topic.topic == "Product Development Strategy"
        assert first_topic.date == datetime(2024, 6, 24, 14, 30, 0)
        assert len(first_topic.points) == 3

        # Test specific point
        elena_point = first_topic.points[0]
        assert elena_point.name == "John Doe"
        assert elena_point.profile_picture == "https://github.com/leerob.png"
        assert "agile sprints" in elena_point.summary

    def test_personal_chat_specific_data(
        self, mock_chat_summaries: list[dict[str, str | list[dict[str, str]]]]
    ):
        """Test specific data from the personal chat mock."""
        personal_chat = ChatSummary(**mock_chat_summaries[1])  # type: ignore

        assert personal_chat.name == "Jane Doe"
        assert len(personal_chat.topics) == 2
        assert personal_chat.chat_type == ChatTypes.PERSONAL

        # Test weekend plans topic
        weekend_topic = personal_chat.topics[0]
        assert weekend_topic.topic == "Weekend Plans"
        assert weekend_topic.date == datetime(2024, 6, 23, 19, 45, 0)
        assert "You" in [point.name for point in weekend_topic.points]

    def test_news_channel_data(
        self, mock_chat_summaries: list[dict[str, str | list[dict[str, str]]]]
    ):
        """Test specific data from the news channel mock."""
        news_channel = ChatSummary(**mock_chat_summaries[2])  # type: ignore

        assert news_channel.name == "TechCrunch"
        assert news_channel.chat_type == ChatTypes.CHANNEL
        assert news_channel.profile_picture == "https://github.com/leerob.png"

        # All points should be from the same entity (news channel)
        for topic in news_channel.topics:
            for point in topic.points:
                assert point.name == "TechCrunch"

    def test_study_group_data(
        self, mock_chat_summaries: list[dict[str, str | list[dict[str, str]]]]
    ):
        """Test specific data from the study group mock."""
        study_group = ChatSummary(**mock_chat_summaries[3])  # type: ignore

        assert study_group.name == "CS Masters 2024"
        assert study_group.chat_type == ChatTypes.GROUP
        assert study_group.profile_picture == "https://github.com/leerob.png"

        # Should have multiple different participants
        all_names: list[str] = []
        for topic in study_group.topics:
            for point in topic.points:
                all_names.append(point.name)

        unique_names = set(all_names)
        assert len(unique_names) == 2

    def test_json_serialization_roundtrip(
        self, mock_chat_summaries: list[dict[str, str | list[dict[str, str]]]]
    ):
        """Test that ChatSummary can be serialized to JSON and back."""
        for chat_data in mock_chat_summaries:
            # Create ChatSummary from JSON
            chat_summary = ChatSummary(**chat_data)  # type: ignore

            # Serialize to JSON
            json_data = chat_summary.model_dump()

            # Create new ChatSummary from serialized data
            recreated_chat = ChatSummary(**json_data)

            # Verify they're equivalent
            assert recreated_chat.name == chat_summary.name
            assert recreated_chat.profile_picture == chat_summary.profile_picture
            assert recreated_chat.chat_type == chat_summary.chat_type
            assert len(recreated_chat.topics) == len(chat_summary.topics)

    def test_invalid_chat_summary(self):
        """Test validation errors for invalid ChatSummary data."""
        invalid_data: dict[str, str | list[dict[str, str]]] = {
            "name": "Test Chat",
            "profile_picture": "not_a_base64_image",
            "chat_type": ChatTypes.GROUP,
            "topics": [],  # Empty topics should be allowed
        }

        # This should still be valid (empty topics is allowed)
        chat_summary = ChatSummary(**invalid_data)  # type: ignore
        assert len(chat_summary.topics) == 0

        # But missing required fields should fail
        with pytest.raises(ValidationError):
            ChatSummary(
                name="Test Chat"
            )  # Missing profile_picture and topics # type: ignore

    def test_empty_topics_list(self):
        """Test that empty topics list is handled correctly."""
        chat_data: dict[str, str | list[dict[str, str]]] = {
            "name": "Empty Chat",
            "profile_picture": "https://github.com/leerob.png",
            "chat_type": ChatTypes.GROUP,
            "topics": [],
        }

        chat_summary = ChatSummary(**chat_data)  # type: ignore
        assert len(chat_summary.topics) == 0
