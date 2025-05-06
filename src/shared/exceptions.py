import logging

logger = logging.getLogger("athena.shared.exceptions")


class HTTPError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP error: {status} - {message}")


class MissingCredentialsError(Exception):
    """Raised when required credentials are missing"""

    def __init__(self, provider: str):
        super().__init__(f"Missing credentials for {provider}")
        self.provider = provider


class EntityAlreadyExistsError(Exception):
    """Raised when an entity already exists"""

    DEFAULT_ENTITY_TYPE = "Entity"

    def __init__(self, entity: str | int, entity_type: str | None = None):
        entity_type = entity_type or self.DEFAULT_ENTITY_TYPE

        if isinstance(entity, int):
            logger.debug("%s object (ID: %s) already exists", entity_type, entity)
            super().__init__(f"{entity_type} object (ID: {entity}) already exists")
        else:
            logger.debug("%s %s already exists", entity_type, entity)
            super().__init__(f"{entity_type} {entity} already exists")
        self.entity = entity


class EntityNotFoundError(Exception):
    """Raised when an entity is not found"""

    def __init__(self, entity_id: str | int):
        if isinstance(entity_id, int):
            logger.debug("Entity with ID %s not found", entity_id)
            super().__init__(f"Entity with ID {entity_id} not found")
        else:
            logger.debug("Entity with ID %s not found", entity_id)
            super().__init__(f"Entity with ID {entity_id} not found")
        self.entity_id = entity_id


class OverloadParametersError(Exception):
    """Raised when the number of provided parameters is >= 1"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
