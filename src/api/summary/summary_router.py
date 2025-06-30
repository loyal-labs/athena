import json
from pathlib import Path

from fastapi import APIRouter

from src.api.summary.summary_schemas import ChatSummary

router = APIRouter()


@router.get("/", response_model=list[ChatSummary])
async def get_chat_summary() -> list[ChatSummary]:
    """
    Get the chat summary for the current user.
    """
    path = Path("tests/api/fixtures/chat_summary_mocks.json")

    with open(path) as f:
        mocked_data = json.load(f)

    return [ChatSummary(**chat_data) for chat_data in mocked_data]
