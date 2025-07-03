from datetime import datetime
from logging import getLogger
from typing import Any

import numpy as np
from pyrogram.enums import ChatType, MessageEntityType, MessageMediaType
from pyrogram.types import Dialog, Message
from sqlalchemy import JSON, BigInteger, ForeignKeyConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

logger = getLogger("telegram.user.summary.summary_schemas")


class TelegramEntity(SQLModel, table=True):
    __tablename__ = "telegram_entities"  # type: ignore

    owner_id: int = Field(sa_type=BigInteger, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, primary_key=True)
    chat_type: str
    title: str | None = None
    username: str | None = None
    small_pfp: str | None = None
    total_messages: int = -1
    unread_count: int = 0
    last_message_date: datetime | None = None
    is_pinned: bool = False
    members_count: int = 1
    is_creator: bool = False
    is_admin: bool = False

    rating: float = 0.0

    @classmethod
    def from_dialog(cls, dialog: Dialog, owner_id: int) -> "TelegramEntity":
        assert dialog.chat.id is not None, "Chat ID is required"
        assert dialog.chat.type is not None, "Chat type is required"

        chat_type: ChatType = dialog.chat.type
        title = (
            dialog.chat.first_name
            if chat_type == ChatType.PRIVATE
            else dialog.chat.title
        )
        username = dialog.chat.username
        small_pfp = dialog.chat.photo.small_file_id if dialog.chat.photo else None

        total_messages = (
            dialog.top_message.id
            if dialog.top_message
            and chat_type in [ChatType.SUPERGROUP, ChatType.CHANNEL]
            else -1
        )
        unread_count = dialog.unread_messages_count or 0
        last_message_date = dialog.top_message.date if dialog.top_message else None
        is_pinned = dialog.is_pinned or False

        members_count = dialog.chat.members_count or 1
        is_creator = dialog.chat.is_creator or False
        is_admin = dialog.chat.is_admin or False

        return cls(
            owner_id=owner_id,
            chat_id=dialog.chat.id,
            chat_type=chat_type.name,
            title=title,
            username=username,
            small_pfp=small_pfp,
            total_messages=total_messages,
            unread_count=unread_count,
            last_message_date=last_message_date,
            is_pinned=is_pinned,
            members_count=members_count,
            is_creator=is_creator,
            is_admin=is_admin,
            rating=0.0,
        )

    async def insert(self, session: AsyncSession) -> "TelegramEntity":
        """Insert a single TelegramEntity into the database."""
        session.add(self)
        await session.commit()
        await session.refresh(self)
        return self

    @classmethod
    async def insert_many(
        cls, entities: list["TelegramEntity"], session: AsyncSession
    ) -> list["TelegramEntity"]:
        """Insert multiple TelegramEntity objects into the database."""
        if not entities:
            return []

        session.add_all(entities)
        await session.commit()

        # Refresh all entities to get any database-generated values
        for entity in entities:
            await session.refresh(entity)

        return entities

    @classmethod
    async def get(
        cls, owner_id: int, chat_id: int, session: AsyncSession
    ) -> "TelegramEntity | None":
        """Get a single TelegramEntity by owner_id and chat_id."""
        result = await session.execute(
            select(cls).where(cls.owner_id == owner_id, cls.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_all_for_owner(
        cls, owner_id: int, session: AsyncSession
    ) -> list["TelegramEntity"]:
        """Get all TelegramEntity records for a specific owner."""
        result = await session.execute(
            select(cls).where(cls.owner_id == owner_id).order_by(cls.rating.desc())  # type: ignore
        )
        return list(result.scalars().all())

    @classmethod
    async def get_filtered(
        cls,
        owner_id: int,
        session: AsyncSession,
        chat_type: str | None = None,
        is_pinned: bool | None = None,
        min_rating: float | None = None,
        limit: int | None = None,
    ) -> list["TelegramEntity"]:
        """Get filtered TelegramEntity records with various criteria."""
        query = select(cls).where(cls.owner_id == owner_id)

        if chat_type is not None:
            query = query.where(cls.chat_type == chat_type)

        if is_pinned is not None:
            query = query.where(cls.is_pinned == is_pinned)

        if min_rating is not None:
            query = query.where(cls.rating >= min_rating)

        query = query.order_by(cls.rating.desc())  # type: ignore

        if limit is not None:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "chat_id"],
            ["telegram_entities.owner_id", "telegram_entities.chat_id"],
        ),
    )

    owner_id: int = Field(sa_type=BigInteger, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, primary_key=True)
    message_id: int = Field(
        sa_type=BigInteger, primary_key=True, description="ID of the message"
    )
    first_name: str | None = Field(None, description="First name of the sender")
    username: str | None = Field(None, description="Username of the sender")
    message: str = Field(description="Message content")
    timestamp: datetime = Field(description="Timestamp of the message")

    # Link preview
    link_preview_title: str | None = Field(
        None, description="Title of the link preview"
    )
    link_preview_description: str | None = Field(
        None, description="Description of the link preview"
    )

    # Negative scores
    is_self: bool = Field(False, description="Whether the message is from the user")
    is_bot: bool = Field(False, description="Whether the message is from a bot")

    # Positive scores
    is_premium: bool = Field(
        False, description="Whether the message is from a premium user"
    )
    is_contact: bool = Field(False, description="Whether the message is from a contact")

    has_mention: bool = Field(
        False, description="Whether the message mentions the user"
    )
    has_link: bool = Field(False, description="Whether the message has a link")

    reaction_count: int = Field(0, description="Number of reactions on the message")
    media_score: int = Field(0, description="Score of the media in the message")

    @property
    def engagement_score(self) -> float:
        """
        Calculate the engagement score of the message
        """
        # --- 1. Feature Preparation (with non-linear transformations) ---

        # Length (using log1p for a smoother curve)
        link_title_length = (
            len(self.link_preview_title) if self.link_preview_title else 0
        )
        link_description_length = (
            len(self.link_preview_description) if self.link_preview_description else 0
        )
        combined_message_length = (
            len(self.message) + link_title_length + link_description_length
        )
        length_score = np.log1p(combined_message_length)

        # Penalize VERY short messages, but still allow for reasonably short ones.
        if combined_message_length < 20:  # Less than ~5 words
            length_score = 0.1  # Small, but non-zero
        else:
            length_score = np.log1p(combined_message_length) / 5.0  # Scale down the log
            length_score = min(length_score, 1.0)  # Limit maximum

        # Reactions (using a modified sigmoid - sharper increase initially)
        reaction_score = 1 / (
            1 + np.exp(-(self.reaction_count - 1) / 2)
        )  # Shift and scale

        # --- 2. Feature Engineering (Interaction Terms) ---
        # TODO: Add later -- it's not that important rn

        # --- 3. Weighted Sum (Weights Optimized for Conversation Importance) ---
        score = (
            0.3 * length_score  # Moderate weight on length (substance)
            - 5.0 * float(self.is_self)  # STRONG penalty for self-messages
            - 3.0 * float(self.is_bot)  # Strong penalty for bot messages (usually)
            + 1.0 * reaction_score  # HIGH weight on reactions (discussion indicator)
            + 0.2
            * float(
                self.is_premium
            )  # Small bonus for premium users (might have higher status)
            + 0.1
            * float(self.is_contact)  # Slight bonus for contacts (more likely relevant)
            + 0.1
            * float(
                self.has_mention
            )  # Small bonus for mentions (targeted conversation)
            + 0.4
            * float(self.has_link)  # Moderate bonus for links (potential information)
            + 0.5 * self.media_score  # Moderate weight on media score (if available)
        )

        # --- 4. Normalization (Min-Max, with adjusted bounds) ---
        # We'll adjust the bounds to reflect the new weights and penalties.
        MIN_SCORE = -5.0  # is_self = True is the main negative driver
        MAX_SCORE = 3.0  # Assuming good length, reactions, and maybe media/link.
        normalized_score = (score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)

        # Clip to 0-1 range, but favor higher scores.
        normalized_score = np.clip(normalized_score, 0.0, 1.0)

        return normalized_score

    @classmethod
    def extract_chat_message_info(
        cls, message_object: Message, owner_id: int, chat_id: int
    ) -> "ChatMessage":
        try:
            message_id = message_object.id
            # We don't handle non-text messages yet
            message = message_object.text
            first_name = (
                message_object.from_user.first_name
                if message_object.from_user
                else None
            )
            username = (
                message_object.from_user.username if message_object.from_user else None
            )
            timestamp = message_object.date

            if message_object.web_page is not None:
                link_preview_title = message_object.web_page.title
                link_preview_description = message_object.web_page.description
            else:
                link_preview_title = None
                link_preview_description = None

            if message_object.from_user is not None:
                is_self = message_object.from_user.is_self
                is_bot = message_object.from_user.is_bot
                is_premium = message_object.from_user.is_premium
                is_contact = message_object.from_user.is_contact
            else:
                is_self = False
                is_bot = False
                is_premium = False
                is_contact = False

            if message_object.media is not None:
                if message_object.media == MessageMediaType.DOCUMENT:
                    media_score = 1
                elif message_object.media == MessageMediaType.PHOTO:
                    media_score = 2
                elif message_object.media == MessageMediaType.VIDEO:
                    media_score = 3
                elif message_object.media == MessageMediaType.AUDIO:
                    media_score = 4
                else:
                    media_score = 0
            else:
                media_score = 0

            has_mention = False
            has_link = False
            if message_object.entities is not None:
                for entity in message_object.entities:
                    if entity.type == MessageEntityType.MENTION:
                        has_mention = True
                    if entity.type == MessageEntityType.URL:
                        has_link = True

            reaction_count = 0
            # if message_object.reactions is not None:
            #     for reaction in message_object.reactions:
            #         reaction_count += reaction.count or 0

            return cls(
                owner_id=owner_id,
                chat_id=chat_id,
                message_id=message_id,
                first_name=first_name,
                username=username,
                message=message or "",
                timestamp=timestamp or datetime.now(),
                link_preview_title=link_preview_title,
                link_preview_description=link_preview_description,
                is_self=is_self,
                is_bot=is_bot,
                is_premium=is_premium,
                is_contact=is_contact,
                has_mention=has_mention,
                has_link=has_link,
                reaction_count=reaction_count,
                media_score=media_score,
            )
        except Exception as e:
            logger.error(f"Error extracting chat message info: {e}")
            raise e

    async def insert(self, session: AsyncSession) -> "ChatMessage":
        """Insert a single ChatMessage into the database."""
        session.add(self)
        await session.commit()
        await session.refresh(self)
        return self

    @classmethod
    async def insert_many(
        cls, messages: list["ChatMessage"], session: AsyncSession
    ) -> list["ChatMessage"]:
        """Insert multiple ChatMessage objects into the database."""
        if not messages:
            return []

        session.add_all(messages)
        await session.commit()

        for message in messages:
            await session.refresh(message)

        return messages

    @classmethod
    async def get(
        cls, owner_id: int, chat_id: int, message_id: int, session: AsyncSession
    ) -> "ChatMessage | None":
        """Get a single ChatMessage by composite primary key."""
        result = await session.execute(
            select(cls).where(
                cls.owner_id == owner_id,
                cls.chat_id == chat_id,
                cls.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_messages_for_chat(
        cls,
        owner_id: int,
        chat_id: int,
        session: AsyncSession,
        limit: int | None = None,
        min_engagement_score: float | None = None,
    ) -> list["ChatMessage"]:
        """Get all messages for a specific chat, optionally filtered."""
        query = (
            select(cls)
            .where(cls.owner_id == owner_id, cls.chat_id == chat_id)
            .order_by(cls.timestamp.desc())  # type: ignore
        )

        if limit is not None:
            query = query.limit(limit)

        result = await session.execute(query)
        messages = list(result.scalars().all())

        # Filter by engagement score if requested
        if min_engagement_score is not None:
            messages = [
                m for m in messages if m.engagement_score >= min_engagement_score
            ]

        return messages  # type: ignore


class ChatSummary(SQLModel, table=True):
    __tablename__ = "chat_summaries"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "chat_id"],
            ["telegram_entities.owner_id", "telegram_entities.chat_id"],
        ),
    )

    owner_id: int = Field(sa_type=BigInteger, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, primary_key=True)
    summary_date: datetime = Field(primary_key=True, default_factory=datetime.now)

    name: str = Field(description="Name of the chat")
    profile_picture: str = Field(description="Base64 profile picture or URL")
    chat_type: str = Field(description="Chat type: personal, group, or channel")
    topics: list[dict[str, Any]] = Field(
        sa_type=JSON, description="JSON array of topics with points"
    )

    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_pipeline_output(
        cls,
        owner_id: int,
        chat_id: int,
        pipeline_output: dict[str, Any],
        profile_picture: str = "",
    ) -> "ChatSummary":
        """Transform pipeline output to ChatSummary for database insertion."""
        # Map chat types
        chat_type_map = {"PRIVATE": "personal", "GROUP": "group", "CHANNEL": "channel"}

        # Transform topics to API format
        topics: list[dict[str, Any]] = []
        for topic in pipeline_output.get("topics", []):
            # Convert key_points to API format
            points: list[dict[str, Any]] = []
            for kp in topic.get("key_points", []):
                points.append(
                    {
                        "name": kp["username"],
                        "profile_picture": "",  # Would need to fetch from TelegramEntity
                        "summary": kp["point"],
                    }
                )

            topics.append(
                {
                    "topic": topic["title"],
                    "date": datetime.now().isoformat(),  # Could use start_time
                    "points": points,
                }
            )

        return cls(
            owner_id=owner_id,
            chat_id=chat_id,
            name=pipeline_output["chat_name"],
            profile_picture=profile_picture,
            chat_type=chat_type_map.get(pipeline_output["chat_type"], "group"),
            topics=topics,
        )

    @classmethod
    async def get_all_for_owner(
        cls, owner_id: int, session: AsyncSession
    ) -> list["ChatSummary"]:
        """Get all ChatSummary records for a specific owner."""
        result = await session.execute(
            select(cls)
            .where(cls.owner_id == owner_id)
            .order_by(cls.summary_date.desc())  # type: ignore
        )

        return list(result.scalars().all())

    async def insert(self, session: AsyncSession) -> "ChatSummary":
        """Insert a single ChatSummary into the database."""
        session.add(self)
        await session.commit()
        await session.refresh(self)
        return self

    @classmethod
    async def insert_many(
        cls, summaries: list["ChatSummary"], session: AsyncSession
    ) -> list["ChatSummary"]:
        """Insert multiple ChatSummary objects into the database."""
        if not summaries:
            return []

        session.add_all(summaries)
        await session.commit()

        for summary in summaries:
            await session.refresh(summary)

        return summaries
