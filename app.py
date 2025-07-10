import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
import uvloop
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.containers import Container, create_container, init_factory, init_service

logger = logging.getLogger("athena.main-app-component")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    logger.info("Starting up the application")

    # --- Container Initialization ---
    logger.info("Initializing container")
    container: Container = create_container()
    # noinspection PyUnresolvedReferences
    app.state.container = container
    secrets_manager = container.secrets_manager()
    secrets_manager = await secrets_manager.create()

    key_service_init_tasks = [
        init_service(container, "observability"),
        init_service(container, "disk_cache_instance"),
        # services with secrets
        init_factory(container, "telegram_factory"),
        init_factory(container, "db_factory"),
        init_factory(container, "llm_factory"),
        init_factory(container, "user_session_factory"),
    ]
    (_, _, telegram, db, _, tg_user_session) = await asyncio.gather(
        *key_service_init_tasks
    )

    # --- Service Initialization ---
    try:
        logger.debug("Initializing services")
        # --- Telegram Bot ---
        message_handlers = container.messages_handlers()
        login_handlers = container.login_handlers()
        handlers = login_handlers.login_handlers + message_handlers.message_handlers
        await telegram.start(handlers=handlers)

        inbox_handlers = container.inbox_handlers()
        await tg_user_session.load_all_sessions(db, inbox_handlers.inbox_filters)

        # --- Database ---

        logger.debug("Services initialized")
    except Exception as e:
        logger.exception("Error initializing services")
        raise e

    yield

    # Shutdown events
    logger.info("Shutting down the application")

    # --- Database Shutdown ---
    try:
        await db.close()
        await tg_user_session.stop_all_sessions()
    except Exception as e:
        logger.exception("Error closing database")
        raise e

    logger.info("Application stopped")


app = FastAPI(
    lifespan=lifespan,
    title="Athena",
    description="Athena API endpoints.",
    version="0.2.0",
    # root_path=shared_config.root_path,
)

# Include the API router
app.include_router(api_router)

# That's for the cors plugin
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "ETag",
        "Cache-Control",
        "If-None-Match",
        "Vary",
        "CDN-Cache-Control",
    ],
)


if __name__ == "__main__":
    # debug startup
    uvicorn.run(app, port=8002)
