import logging
import pkgutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dependency_injector import containers, providers

from src.shared.base import BaseService
from src.shared.base_llm import LLMFactory
from src.shared.cache import get_disk_cache
from src.shared.database import DatabaseFactory
from src.shared.event_bus import EventBus
from src.shared.logging_utils import configure_logging
from src.shared.secrets import OnePasswordManager
from src.telegram.bot.client.telegram_bot import TelegramBotFactory
from src.telegram.bot.login.login_handlers import LoginHandlers
from src.telegram.bot.messages.messages_handlers import MessageHandlers
from src.telegram.user.inbox.inbox_handlers import TelegramUserMessageHandlers
from src.telegram.user.telegram_session_manager import UserSessionFactory

logger = logging.getLogger("athena.containers")


class Container(containers.DeclarativeContainer):
    # -- SECRETS --
    secrets_manager = providers.Singleton(OnePasswordManager)

    # # --- DATABASE ---

    db_factory = providers.Singleton(DatabaseFactory)

    # -- Disk Cache --
    disk_cache_instance = providers.Singleton(get_disk_cache)

    # -- Event Bus --
    event_bus = providers.Singleton(EventBus)

    # -- Observability --
    observability = providers.Factory(configure_logging)

    # -- Telegram --
    telegram_factory = providers.Singleton(TelegramBotFactory)
    messages_handlers = providers.Singleton(MessageHandlers)
    login_handlers = providers.Singleton(LoginHandlers)

    # -- Telegram Users --
    user_session_factory = providers.Singleton(UserSessionFactory)
    inbox_handlers = providers.Singleton(TelegramUserMessageHandlers)

    # -- LLM Providers --
    llm_factory = providers.Singleton(LLMFactory)


def find_modules_in_packages(packages_paths: list[str]) -> list[str]:
    """
    Finds all module names within the specified package paths.

    Args:
        packages_paths: A list of dotted package paths

    Returns:
        A list of fully qualified module names found within those packages.
    """
    discovered_modules = set[str]()
    project_root = Path(__file__).parent.parent
    for package_path in packages_paths:
        try:
            package_parts = package_path.split(".")
            package_dir = project_root.joinpath(*package_parts)

            for _, name, ispkg in pkgutil.walk_packages(
                path=[str(package_dir)],
                prefix=package_path + ".",
            ):
                if not ispkg:
                    discovered_modules.add(name)

        except ModuleNotFoundError:
            logger.warning(
                "Warning: Package path %s not found or not a package.", package_path
            )
        except Exception as e:
            logger.warning(
                "Warning: Error scanning package %s: %s",
                package_path,
                e,
            )

    discovered_modules = list(discovered_modules)
    discovered_modules_len = len(discovered_modules)
    if discovered_modules_len == 0:
        logger.critical("No modules found for wiring in %s", project_root)
    else:
        logger.debug("Discovered modules for wiring: %s", discovered_modules_len)
    return discovered_modules


def create_container() -> Container:
    """Creates and wires the dependency injection container."""
    logger.debug("Creating dependency injection container")
    container = Container()

    packages_to_wire = [
        "src.shared",
        "src.telegram",
        "src.telegraph",
        "src.telemetree",
    ]
    modules_to_wire = find_modules_in_packages(packages_to_wire)  # type: ignore
    container.wire(modules=modules_to_wire)

    logger.debug("Container wired")
    return container


async def init_factory(container: Container, name: str) -> Any:
    """
    Initializes a factory.
    """
    factory_dict = {
        "db_factory": container.db_factory,
        "llm_factory": container.llm_factory,
        "telegram_factory": container.telegram_factory,
        "user_session_factory": container.user_session_factory,
    }

    assert name is not None, "Factory name is not set"
    assert name in factory_dict, f"Factory {name} not found in container"

    try:
        logger.debug("Initializing factory %s", name)

        factory_object = factory_dict[name]()
        factory = await factory_object.get_instance()

        logger.debug("Initialized factory %s", name)
        return factory
    except KeyError as e:
        raise ValueError("Factory %s not found in container", name) from e
    except Exception as e:
        logger.exception("Error initializing factory %s", name)
        raise e


async def init_service(
    container: Container,
    name: str,
) -> Any:
    """
    Initializes a service.
    """

    service_dict = {
        "observability": container.observability,
        "disk_cache_instance": container.disk_cache_instance,
        "event_bus": container.event_bus,
    }

    assert name is not None, "Service name is not set"
    assert name in service_dict, f"Service {name} not found in container"

    try:
        logger.debug("Initializing service %s", name)
        service = service_dict[name]()
        logger.debug("Initialized service %s", name)

        return service
    except KeyError as e:
        raise ValueError("Service %s not found in container", name) from e
    except Exception as e:
        logger.exception("Error initializing service %s", name)
        raise e


async def init_service_and_register(
    service_factory: Callable[[], BaseService], event_bus: EventBus
) -> None:
    """
    Initializes a service and registers it with the event bus.

    Args:
        service_factory: A callable that returns a BaseService instance.
        event_bus: The event bus to register the service with.
    """
    service = service_factory()
    event_bus.register_subscribers_from(service)
    logger.debug("Initialized and registered %s", service.__class__.__name__)
