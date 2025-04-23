import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
import uvloop
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.containers import (
    Container,
    create_container,
    init_service,
    init_service_and_register,
)
from src.shared.config import shared_config

logger = logging.getLogger("athena.main-app-component")

# --- Event Loop Initialization ---
uvloop.install()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up the application")
    logger.info("App environment: %s", shared_config.app_env)
    logger.info("Debug mode: %s", shared_config.debug_mode)

    logger.info("Event bus type: %s", shared_config.event_bus)

    # --- Container Initialization ---
    logger.info("Initializing container")
    container: Container = create_container()
    # noinspection PyUnresolvedReferences
    app.state.container = container

    key_service_init_tasks = [
        init_service(container, "observability"),
        init_service(container, "db"),
        init_service(container, "telegram_object"),
        init_service(container, "event_bus"),
        init_service(container, "disk_cache_instance"),
    ]
    (
        _,
        db_instance,
        telegram_object,
        event_bus,
        _,
    ) = await asyncio.gather(*key_service_init_tasks)

    # --- Service Initialization ---
    try:
        logger.debug("Initializing services")
        message_handlers = container.message_handlers()

        async_service_start_tasks = [
            db_instance.create_all(),
            telegram_object.start(handlers=message_handlers.message_handlers),
        ]

        async_init_tasks = [
            init_service_and_register(container.messages_service, event_bus),
            init_service_and_register(container.posts_service, event_bus),
        ]

        async_tasks = [
            *async_service_start_tasks,
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
    try:
        await db_instance.close()
    except Exception as e:
        logger.exception("Error closing database")
        raise e

    logger.info("Application stopped")


app = FastAPI(
    lifespan=lifespan,
    title="Telemetree API",
    description="Telemetree API endpoints.",
    version="1.0.0",
    root_path=shared_config.root_path,
)

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
