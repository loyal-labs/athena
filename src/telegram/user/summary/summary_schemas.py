from datetime import datetime

from pyrogram.enums import ChatType
from pyrogram.types import Dialog
from sqlmodel import Field, SQLModel


class TelegramEntity(SQLModel, table=True):
    __tablename__ = "telegram_entities"  # type: ignore

    chat_id: int = Field(primary_key=True)
    chat_type: str
    title: str | None = None
    username: str | None = None
    small_pfp: str | None = None
    total_messages: int = -1
    unread_count: int = 0
    last_message_date: datetime | None = None
    is_pinned: bool = False
    members_count: int | None = None
    is_creator: bool = False
    is_admin: bool = False

    rating: float = 0.0

    @classmethod
    def from_dialog(cls, dialog: Dialog) -> "TelegramEntity":
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

        members_count = getattr(dialog.chat, "members_count", None)
        is_creator = getattr(dialog.chat, "is_creator", False)
        is_admin = getattr(dialog.chat, "is_admin", False)

        return cls(
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
