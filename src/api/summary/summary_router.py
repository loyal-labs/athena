import json
from pathlib import Path

from fastapi import APIRouter

from src.api.summary.summary_schemas import ChatSummary

router = APIRouter()


@router.get("/", response_model=ChatSummary)
async def get_chat_summary() -> ChatSummary:
    """
    Get the chat summary for the current user.
    """
    path = (
        Path(__file__).parent.parent.parent
        / "tests"
        / "api"
        / "fixtures"
        / "chat_summary_mocks.json"
    )

    with open(path) as f:
        return ChatSummary(**json.load(f))
