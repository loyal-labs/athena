import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
import uvloop
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.containers import (
    Container,
    create_container,
    init_service,
    init_service_and_register,
)

logger = logging.getLogger("athena.main-app-component")

# --- Event Loop Initialization ---
uvloop.install()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
        init_service(container, "event_bus"),
        init_service(container, "disk_cache_instance"),
        # services with secrets
        init_service(container, "telegram_object", secrets_manager),
        # init_service(container, "db", secrets_manager),
    ]
    (
        _,
        event_bus,
        _,
        telegram,
        # db,
    ) = await asyncio.gather(*key_service_init_tasks)

    # --- Service Initialization ---
    try:
        logger.debug("Initializing services")
        # --- Telegram ---
        message_handlers = container.message_handlers()
        # await telegram.start(handlers=message_handlers.message_handlers)  # type: ignore

        # --- Database ---

        async_init_tasks = [
            init_service_and_register(container.messages_service, event_bus),
            init_service_and_register(container.posts_service, event_bus),
        ]

        async_tasks = [
            *async_init_tasks,
        ]

        await asyncio.gather(*async_tasks)

        logger.debug("Services initialized")
    except Exception as e:
        logger.exception("Error initializing services")
        raise e

    yield

    # Shutdown events
    logger.info("Shutting down the application")

    # --- Database Shutdown ---
    # try:
    #     await db.close()
    # except Exception as e:
    #     logger.exception("Error closing database")
    #     raise e

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
