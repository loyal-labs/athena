from datetime import datetime
from logging import getLogger
from typing import Any

from pyrogram.enums import ChatType
from pyrogram.types import Chat, Dialog, Message
from sqlalchemy import JSON, BigInteger, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlmodel import Field, Relationship, SQLModel, col, func, select, update

logger = getLogger("telegram.user.summary.summary_schemas")


class TelegramEntity(SQLModel, table=True):
    __tablename__ = "telegram_entities"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"],
            ["telegram_sessions.owner_id"],
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

    # Relationships to child tables
    chat_messages: list["TelegramMessage"] = Relationship(
        back_populates="telegram_entity",
        sa_relationship_kwargs={"lazy": "select", "cascade": "all, delete-orphan"},
    )
    chat_summaries: list["TelegramChatSummary"] = Relationship(
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
    async def get_unread(
        cls, owner_id: int, session: AsyncSession
    ) -> list["TelegramEntity"]:
        """Get all unread TelegramEntity records for a specific owner."""
        result = await session.execute(
            select(cls)
            .where(cls.owner_id == owner_id, cls.unread_count > 0)
            .order_by(cls.rating.desc(), cls.last_message_date.desc())  # type: ignore
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


class TelegramMessage(SQLModel, table=True):
    __tablename__ = "telegram_messages"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "chat_id"],
            ["telegram_entities.owner_id", "telegram_entities.chat_id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint(
            "owner_id", "chat_id", "message_id", name="pk_telegram_messages"
        ),
    )

    owner_id: int = Field(sa_type=BigInteger)
    chat_id: int = Field(sa_type=BigInteger)
    message_id: int = Field(sa_type=BigInteger, description="ID of the message")

    title: str | None = Field(None, description="Title of the sender")
    username: str | None = Field(None, description="Username of the sender")
    message: str = Field(description="Message content")
    timestamp: datetime = Field(description="Timestamp of the message")
    is_read: bool = Field(default=False, description="Whether the message is read")

    # Relationship to TelegramEntity
    telegram_entity: "TelegramEntity" = Relationship(
        back_populates="chat_messages", sa_relationship_kwargs={"lazy": "select"}
    )

    @classmethod
    def extract_chat_message_info(
        cls, message_object: Message, owner_id: int, chat_id: int, is_read: bool = False
    ) -> "TelegramMessage":
        try:
            message_id = message_object.id
            # We don't handle non-text messages yet
            message = message_object.text or message_object.caption or ""
            if message_object.from_user:
                title = message_object.from_user.first_name
            elif message_object.channel_post:
                assert message_object.chat is not None, "Chat is required"
                title = message_object.chat.title or None
            else:
                title = None

            if message_object.from_user:
                username = message_object.from_user.username
            elif message_object.channel_post:
                assert message_object.chat is not None, "Chat is required"
                username = message_object.chat.username or None
            else:
                username = None

            timestamp = message_object.date

            return cls(
                owner_id=owner_id,
                chat_id=chat_id,
                message_id=message_id,
                title=title,
                username=username,
                message=message or "",
                timestamp=timestamp or datetime.now(),
                is_read=is_read,
            )
        except Exception as e:
            logger.error(f"Error extracting chat message info: {e}")
            raise e

    async def insert(self, session: AsyncSession) -> "TelegramMessage":
        """Insert a single ChatMessage into the database."""
        session.add(self)
        await session.commit()
        await session.refresh(self)
        return self

    @classmethod
    async def insert_many(
        cls,
        messages: list["TelegramMessage"],
        session: AsyncSession,
        commit: bool = True,
    ) -> list["TelegramMessage"]:
        """Insert multiple ChatMessage objects into the database."""
        if not messages:
            return []

        value_dicts = [message.model_dump() for message in messages]

        insert_statement = pg_insert(cls).values(value_dicts)

        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["owner_id", "chat_id", "message_id"],
            set_={
                "title": insert_statement.excluded.title,
                "username": insert_statement.excluded.username,
                "message": insert_statement.excluded.message,
                "timestamp": insert_statement.excluded.timestamp,
            },
        )

        await session.execute(upsert_statement)
        if commit:
            await session.commit()

        return messages

    @classmethod
    async def get(
        cls, owner_id: int, chat_id: int, message_id: int, session: AsyncSession
    ) -> "TelegramMessage | None":
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
    async def get_unique_chat_ids(
        cls, owner_id: int, session: AsyncSession
    ) -> list[int]:
        """Get all unique chat IDs for a specific owner."""
        query = select(func.distinct(cls.chat_id)).where(cls.owner_id == owner_id)
        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_all_for_owner(
        cls, owner_id: int, session: AsyncSession, join_entity: bool = False
    ) -> list["TelegramMessage"]:
        """Get all ChatMessage records for a specific owner."""
        query = (
            select(cls).where(cls.owner_id == owner_id).order_by(cls.timestamp.desc())  # type: ignore
        )  # type: ignore

        if join_entity:
            query = query.options(joinedload(cls.telegram_entity))  # type: ignore

        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_messages_for_chat(
        cls,
        owner_id: int,
        chat_id: int,
        session: AsyncSession,
        limit: int | None = None,
    ) -> list["TelegramMessage"]:
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
        print(messages)

        return messages  # type: ignore

    @staticmethod
    def messages_to_text(messages: list["TelegramMessage"]) -> str:
        """Convert a list of TelegramMessage objects to a text string."""
        return_string = ""

        for message in messages:
            print(message)
            text = message.message
            if not text or len(text) == 0:
                continue

            text = text.replace("\n", " ")
            timestamp = message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            author = message.title or message.username or "Unknown"
            return_string += f"{timestamp} - {author}: {text}\n"

        return return_string


class TelegramChatSummary(SQLModel, table=True):
    __tablename__ = "telegram_chat_summaries"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "chat_id"],
            ["telegram_entities.owner_id", "telegram_entities.chat_id"],
            ondelete="CASCADE",
        ),
    )

    owner_id: int = Field(sa_type=BigInteger, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, primary_key=True)

    topics: list[dict[str, Any]] | None = Field(
        sa_type=JSON, description="JSON array of topics with points", nullable=True
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
    ) -> "TelegramChatSummary":
        """Transform pipeline output to ChatSummary for database insertion."""

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
            topics=topics,
        )

    @classmethod
    async def get_all_for_owner(
        cls, owner_id: int, session: AsyncSession, join_entity: bool = False
    ) -> list["TelegramChatSummary"]:
        """Get all ChatSummary records for a specific owner."""
        query = (
            select(cls).where(cls.owner_id == owner_id).order_by(cls.chat_id.desc())  # type: ignore
        )

        if join_entity:
            query = query.options(joinedload(cls.telegram_entity))  # type: ignore

        result = await session.execute(query)

        return list(result.scalars().all())

    @classmethod
    async def get_chat_with_offset(
        cls, owner_id: int, session: AsyncSession, offset: int
    ) -> list["TelegramChatSummary"]:
        """Get a ChatSummary record for a specific owner with an offset."""
        query = (
            select(cls)
            .where(cls.owner_id == owner_id)
            .order_by(cls.chat_id.desc())  # type: ignore
            .offset(offset)
            .limit(1)
            .options(joinedload(cls.telegram_entity))  # type: ignore
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def choose_unread_non_processed_summary(
        cls, owner_id: int, session: AsyncSession, limit: int = 1
    ) -> list["TelegramChatSummary"]:
        """Choose an unread non-processed summary for a specific owner."""
        stmt = (
            select(cls)
            .where(
                cls.owner_id == owner_id,
                cls.is_processed == False,  # noqa: E712
                cls.is_read == False,  # noqa: E712
            )
            .order_by(cls.created_at.desc())  # type: ignore
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def count_processed_unread_summary(
        cls, owner_id: int, session: AsyncSession
    ) -> int:
        """Count the number of processed summaries for a specific owner."""
        stmt = (
            select(func.count())
            .select_from(cls)
            .where(
                cls.owner_id == owner_id,
                cls.is_processed == True,  # noqa: E712
                cls.is_read == False,  # noqa: E712
            )
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none() or 0

    @classmethod
    async def count_unread_summaries(cls, owner_id: int, session: AsyncSession) -> int:
        """Count the number of unread summaries for a specific owner."""
        stmt = (
            select(func.count())
            .select_from(cls)
            .where(cls.owner_id == owner_id, not cls.is_read == False)  # noqa: E712
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none() or 0

    @classmethod
    async def insert_empty(
        cls, owner_id: int, chats_ids: list[int], session: AsyncSession
    ) -> None:
        """Insert empty chat summaries for a list of chats."""
        summaries: list[TelegramChatSummary] = []
        for chat_id in chats_ids:
            summaries.append(
                cls(
                    owner_id=owner_id,
                    chat_id=chat_id,
                    topics=[],
                )
            )

        logger.debug(f"Inserting {len(summaries)} empty chat summaries")

        await cls.insert_many(summaries, session)

    @classmethod
    async def from_telegram_entity(
        cls, entity: "TelegramEntity"
    ) -> "TelegramChatSummary":
        """Create a ChatSummary from a TelegramEntity."""
        return cls(
            owner_id=entity.owner_id,
            chat_id=entity.chat_id,
            topics=[],
            is_read=False,
            is_processed=False,
            created_at=datetime.now(),
        )

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

    @classmethod
    async def update_topics(
        cls, value: "TelegramChatSummary", session: AsyncSession
    ) -> None:
        """Update the topics for a ChatSummary."""
        stmt = (
            update(cls)
            .where(
                col(cls.owner_id) == value.owner_id,
                col(cls.chat_id) == value.chat_id,
            )
            .values(topics=value.topics)
        )
        await session.execute(stmt)
        await session.commit()

    async def insert(self, session: AsyncSession) -> "TelegramChatSummary":
        """Insert a single ChatSummary into the database."""
        session.add(self)
        await session.commit()
        await session.refresh(self)
        return self

    @classmethod
    async def insert_many(
        cls, summaries: list["TelegramChatSummary"], session: AsyncSession
    ) -> list["TelegramChatSummary"]:
        """Insert multiple ChatSummary objects into the database."""
        if not summaries:
            return []

        session.add_all(summaries)
        await session.commit()

        for summary in summaries:
            await session.refresh(summary)

        return summaries
