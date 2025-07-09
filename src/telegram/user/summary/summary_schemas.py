from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any

from pyrogram.enums import ChatType
from pyrogram.types import Chat, Dialog, Message
from sqlalchemy import JSON, BigInteger, ForeignKeyConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Relationship, SQLModel, select

if TYPE_CHECKING:
    from src.telegram.user.login.login_schemas import LoginSession

logger = getLogger("telegram.user.summary.summary_schemas")


class TelegramEntity(SQLModel, table=True):
    __tablename__ = "telegram_entities"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"],
            ["login_sessions.owner_id"],
            ondelete="CASCADE",
        ),
    )

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

    # Relationship to LoginSession
    login_session: "LoginSession" = Relationship(
        back_populates="telegram_entities", sa_relationship_kwargs={"lazy": "select"}
    )

    # Relationships to child tables
    chat_messages: list["ChatMessage"] = Relationship(
        back_populates="telegram_entity",
        sa_relationship_kwargs={"lazy": "select", "cascade": "all, delete-orphan"},
    )
    chat_summaries: list["ChatSummary"] = Relationship(
        back_populates="telegram_entity",
        sa_relationship_kwargs={"lazy": "select", "cascade": "all, delete-orphan"},
    )

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

    @classmethod
    def from_chat(cls, chat: Chat, message: Message, owner_id: int) -> "TelegramEntity":
        assert chat.id is not None, "Chat ID is required"
        assert chat.type is not None, "Chat type is required"

        chat_type: ChatType = chat.type
        if chat_type == ChatType.PRIVATE:
            assert message.from_user is not None, "Message from user is required"
            title = message.from_user.first_name
        else:
            title = chat.title

        username = chat.username or None
        small_pfp = chat.photo.small_file_id if chat.photo else None

        # TODO: if it's channel or supergroup, take it from the message
        if chat_type in [ChatType.SUPERGROUP, ChatType.CHANNEL]:
            total_messages = message.id
        else:
            total_messages = -1

        unread_count = chat.unread_count or 0
        last_message_date = datetime.now()
        is_pinned = False

        members_count = chat.members_count or 1
        is_creator = chat.is_creator or False
        is_admin = chat.is_admin or False

        return cls(
            owner_id=owner_id,
            chat_id=chat.id,
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
            ondelete="CASCADE",
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

    # Relationship to TelegramEntity
    telegram_entity: "TelegramEntity" = Relationship(
        back_populates="chat_messages", sa_relationship_kwargs={"lazy": "select"}
    )

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

            return cls(
                owner_id=owner_id,
                chat_id=chat_id,
                message_id=message_id,
                first_name=first_name,
                username=username,
                message=message or "",
                timestamp=timestamp or datetime.now(),
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
    async def get_all_for_owner(
        cls, owner_id: int, session: AsyncSession
    ) -> list["ChatMessage"]:
        """Get all ChatMessage records for a specific owner."""
        result = await session.execute(
            select(cls).where(cls.owner_id == owner_id).order_by(cls.timestamp.desc())  # type: ignore
        )
        return list(result.scalars().all())

    @classmethod
    async def get_messages_for_chat(
        cls,
        owner_id: int,
        chat_id: int,
        session: AsyncSession,
        limit: int | None = None,
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

        return messages  # type: ignore


class ChatSummary(SQLModel, table=True):
    __tablename__ = "chat_summaries"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "chat_id"],
            ["telegram_entities.owner_id", "telegram_entities.chat_id"],
            ondelete="CASCADE",
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

    is_read: bool = Field(default=False)
    is_processed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now)

    # Relationship to TelegramEntity
    telegram_entity: "TelegramEntity" = Relationship(
        back_populates="chat_summaries", sa_relationship_kwargs={"lazy": "select"}
    )

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
                        "profile_picture": "",
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

    @classmethod
    async def get_processed_for_owner(
        cls, owner_id: int, session: AsyncSession, limit: int | None = None
    ) -> list["ChatSummary"]:
        """Get processed ChatSummary records for a specific owner."""
        query = (
            select(cls)
            .where(cls.owner_id == owner_id, cls.is_processed == True)
            .order_by(cls.created_at.asc())  # type: ignore
        )

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_unprocessed_for_owner(
        cls, owner_id: int, session: AsyncSession, limit: int | None = None
    ) -> list["ChatSummary"]:
        """Get unprocessed ChatSummary records for a specific owner."""
        query = (
            select(cls)
            .where(cls.owner_id == owner_id, cls.is_processed == False)
            .order_by(cls.created_at.asc())  # type: ignore
        )

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def mark_as_processed(
        cls, owner_id: int, chat_id: int, session: AsyncSession
    ) -> None:
        """Mark a ChatSummary as processed."""
        result = await session.execute(
            select(cls).where(cls.owner_id == owner_id, cls.chat_id == chat_id)
        )
        summary = result.scalar_one_or_none()
        if summary:
            summary.is_processed = True
            await session.commit()

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
