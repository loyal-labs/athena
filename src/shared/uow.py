import contextvars
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.types import SessionFactory

current_uow: contextvars.ContextVar["UnitOfWork | None"] = contextvars.ContextVar(
    "current_uow", default=None
)

logger = logging.getLogger("athena.uow")


class UnitOfWork:
    """Manages a single session and transaction for a unit of work."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._context_token: contextvars.Token[UnitOfWork | None] | None = None

    async def get_session(self) -> AsyncSession:
        """Returns the active session, raising an error if not started."""
        if self._session is None:
            # This indicates get_session was called outside 'start' context
            raise RuntimeError(
                "UnitOfWork session has not been started or is already closed."
            )
        return self._session

    @asynccontextmanager
    async def start(self) -> AsyncIterator["UnitOfWork"]:
        """Starts a new transaction context for this Unit of Work."""
        if self._session is not None:
            raise RuntimeError("UnitOfWork session is already active.")

        self._context_token = current_uow.set(self)
        logger.debug("UoW context started, token set: %s", self._context_token)

        async with self._session_factory() as session:
            self._session = session
            logger.debug("UoW acquired session: %s", session)
            try:
                yield self  # The UoW instance itself
                logger.debug("UoW exiting cleanly, session %s will commit.", session)
            except Exception:
                logger.error(
                    "UoW caught exception, session %s will roll back.",
                    session,
                    exc_info=True,
                )
                raise
            finally:
                logger.debug("UoW cleaning up (token: %s)...", self._context_token)
                self._session = None
                if self._context_token:
                    try:
                        current_uow.reset(self._context_token)
                        logger.debug("UoW context variable reset.")
                    except ValueError:
                        logger.warning(
                            "Failed to reset UoW (token: %s)",
                            self._context_token,
                        )
                    self._context_token = None
