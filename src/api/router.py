from fastapi import APIRouter

from src.api.summary.summary_router import router as summary_router

api_router = APIRouter()
api_router.include_router(summary_router, prefix="/summary", tags=["Chat Summary"])


@api_router.get("/ping")
async def ping():
    return {"message": "pong"}
