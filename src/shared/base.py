import logging
from datetime import datetime
from random import randint
from typing import Any, Generic, TypeVar, overload

from pydantic import ValidationError
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, col, exists, select

from src.shared.exceptions import EntityAlreadyExistsError, EntityNotFoundError

logger = logging.getLogger("athena.base-components")

T = TypeVar("T", bound="BaseSchema")


class BaseSchema(SQLModel):
    object_id: int = Field(
        primary_key=True, default_factory=lambda: randint(1, 100000000), index=True
    )

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class BaseService:
    """
    A base class for services that automatically registers event bus subscribers.
    """

    def __init__(self) -> None:
        """
        Initializes the service and registers its decorated event handlers.
        """
        logger.debug(
            f"Automatically registered subscribers from {self.__class__.__name__}"
        )


class BaseModel(Generic[T]):
    def __init__(self, model_class: type[T]):
        self.model_class = model_class

    def __dict_keys(self) -> list[str]:
        return [
            key for key in self.model_class.__dict__.keys() if not key.startswith("_")
        ]

    @overload
    async def add(
        self, session: AsyncSession, entity: T, pass_checks: bool = True
    ) -> list[T]: ...

    @overload
    async def add(self, session: AsyncSession, entity: list[T]) -> list[T]: ...

    async def add(
        self, session: AsyncSession, entity: T | list[T], pass_checks: bool = True
    ) -> list[T] | None:
        """
        Adds an entity to the session. Needs to be flushed.
        Great for adding dependent entities.

        Args:
            session: The session to add the entity to.
            entity: The entity to add.

        Returns:
            The added entity.
        """
        try:
            assert entity
        except AssertionError as e:
            logger.error("Error adding entity: %s", e)
            raise ValueError("Invalid entity") from e

        if isinstance(entity, list):
            # TODO: Adapt the single-entity logic to the many-entity logic
            return await self.add_many(session, entity)
        else:
            try:
                response = await self.add_one(session, entity, pass_checks)

                object_id = response[0].object_id
                object_name = self.model_class.__name__
                logger.debug("Added %s to session: %s", object_name, object_id)
                return response
            except EntityAlreadyExistsError:
                return None
            except Exception as e:
                logger.error("Error adding entity: %s", e)
                raise e

    async def add_one(
        self, session: AsyncSession, entity: T, pass_checks: bool = True
    ) -> list[T]:
        """Adds an entity to the session. Needs to be flushed."""
        try:
            if pass_checks:
                checked_entity = await self.pass_insert_checks(session, entity)
            else:
                checked_entity = entity
        except EntityAlreadyExistsError as e:
            raise e
        except Exception as e:
            logger.error("Error adding entity to session: %s", e)
            raise e

        session.add(checked_entity)
        logger.debug("Added entity to session: %s", checked_entity)
        return [checked_entity]

    async def add_many(self, session: AsyncSession, entities: list[T]) -> list[T]:
        """Adds a list of entities to the session. Needs to be flushed."""
        try:
            checked_entities = await self.pass_insert_checks(session, entities)
        except Exception as e:
            logger.error("Error adding entities to session: %s", e)
            raise e

        session.add_all(checked_entities)
        logger.debug("Added entities to session: %s", checked_entities)
        return checked_entities

    # TODO: fix this into a more pythonic way: https://t.me/c/2692177928/1041
    async def get_by_other_params(
        self, session: AsyncSession, **kwargs: Any
    ) -> list[Any]:
        """Gets an entity by other parameters."""
        try:
            assert kwargs
            assert all(key in self.__dict_keys() for key in kwargs.keys())
        except AssertionError as e:
            logger.error("Error getting entity by other parameters: %s", e)
            raise e

        query = select(self.model_class).where(
            *[getattr(self.model_class, key) == value for key, value in kwargs.items()]
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_by_param_in_list(
        self, session: AsyncSession, param: str, values: list[Any]
    ) -> list[Any]:
        """Gets an entity by a field that is a list."""
        valid_keys = self.__dict_keys()
        try:
            assert param in valid_keys
        except AssertionError as e:
            logger.error("Error getting entity by param in list: %s", e)
            raise e

        try:
            param_attr = getattr(self.model_class, param)
            query = select(self.model_class).where(param_attr.in_(values))
            result = await session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error("Error getting entity by param in list: %s", e)
            raise e

    async def get_by_id(self, session: AsyncSession, entity_id: int) -> list[Any]:
        """Gets an entity by its ID."""
        try:
            assert entity_id
            assert isinstance(entity_id, int)
        except AssertionError as e:
            logger.error("Error getting entity by ID: %s", e)
            raise ValueError("Invalid entity ID") from e

        query = select(self.model_class).where(self.model_class.object_id == entity_id)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_all(self, session: AsyncSession) -> list[Any]:
        """Gets all entities."""
        query = select(self.model_class)
        result = await session.execute(query)
        return_value = list(result.scalars().all())
        return return_value

    @overload
    async def create(self, session: AsyncSession, entity: T) -> list[T]: ...

    @overload
    async def create(self, session: AsyncSession, entity: list[T]) -> list[T]: ...

    async def create(self, session: AsyncSession, entity: T | list[T]) -> list[T]:
        """
        Creates an entity in the database and flushes the session.

        Args:
            session: The session to add the entity to.
            entity: The entity to create.

        Returns:
            The created entity.
        """
        try:
            assert entity
        except AssertionError as e:
            logger.error("Error creating entity: %s", e)
            raise e

        if isinstance(entity, list):
            response = await self.add_many(session, entity)
            await session.flush()
            await session.refresh(response)
            logger.debug("Created entities in session: %s", response)
            return response
        else:
            response = await self.add_one(session, entity)
            await session.flush()
            await session.refresh(response)
            logger.debug("Created entity in session: %s", len(response))
            return response

    @overload
    async def remove(self, session: AsyncSession, entity: None) -> bool: ...

    @overload
    async def remove(self, session: AsyncSession, entity: T) -> bool: ...

    @overload
    async def remove(self, session: AsyncSession, entity: list[T]) -> bool: ...

    async def remove(self, session: AsyncSession, entity: list[T] | T | None) -> bool:
        """Removes an entity from the session."""
        try:
            assert entity
        except AssertionError as e:
            logger.error("Error removing entity: %s", e)
            raise ValueError("Invalid entity") from e

        if not entity:
            return await self.__remove_all(session)
        elif isinstance(entity, list):
            return await self.__remove_many(session, entity)
        else:
            return await self.__remove_one(session, entity.object_id)

    async def __remove_one(self, session: AsyncSession, entity_id: int) -> bool:
        """Private method. Removes an entity by its ID."""
        try:
            assert isinstance(entity_id, int)
        except AssertionError as e:
            logger.error("Error removing entity: %s", e)
            raise ValueError("Invalid entity ID") from e

        statement = select(self.model_class).where(
            self.model_class.object_id == entity_id
        )
        result = await session.execute(statement)
        entity = result.scalars().first()

        try:
            assert entity
        except AssertionError as e:
            logger.error("Error removing entity: %s", e)
            raise EntityNotFoundError(entity_id) from e

        await session.delete(entity)
        return True

    async def __remove_many(self, session: AsyncSession, entities: list[T]) -> bool:
        """Private method. Removes entities by their IDs."""
        try:
            assert entities
            assert all(isinstance(entity.object_id, int) for entity in entities)
        except AssertionError as e:
            logger.error("Error removing entities: %s", e)
            raise ValueError("All entity IDs must be integers") from e

        entity_ids = [entity.object_id for entity in entities]
        statement = select(self.model_class).where(
            col(self.model_class.object_id).in_(entity_ids)
        )
        result = await session.execute(statement)
        entities = list(result.scalars().all())

        try:
            assert entities
            assert all(isinstance(entity.object_id, int) for entity in entities)
        except AssertionError as e:
            logger.error("Error removing entities: %s", e)
            raise ValueError("All entity IDs must be integers") from e

        for entity in entities:
            await session.delete(entity)
        return True

    async def __remove_all(self, session: AsyncSession) -> bool:
        """Private method. Removes all entities."""
        statement = delete(self.model_class)
        await session.execute(statement)

        try:
            assert await self.__table_is_empty(session)
        except AssertionError as e:
            logger.error("Error removing all entities: %s", e)
            raise e

        return True

    @overload
    async def is_present(self, session: AsyncSession, entity_id: int) -> bool: ...

    @overload
    async def is_present(self, session: AsyncSession, **kwargs: Any) -> bool: ...

    async def is_present(
        self, session: AsyncSession, entity_id: int | None = None, **kwargs: Any
    ) -> bool:
        """Checks if an entity exists by its ID or other parameters."""
        if entity_id:
            return await self.is_present_one(session, entity_id)
        else:
            return await self.is_present_many(session, **kwargs)

    async def is_present_one(self, session: AsyncSession, entity_id: int) -> bool:
        """Checks if an entity exists by its ID."""
        result = await self.get_by_id(session, entity_id)
        try:
            assert result
            assert len(result) != 0
            return True
        except AssertionError:
            return False
        except Exception as e:
            logger.error("Error checking if entity is present: %s", e)
            raise e

    async def is_present_many(self, session: AsyncSession, **kwargs: Any) -> bool:
        """Checks if an entity exists by other parameters."""
        result = await self.get_by_other_params(session, **kwargs)
        try:
            assert result
            assert len(result) != 0
            return True
        except AssertionError:
            return False
        except Exception as e:
            logger.error("Error checking if entity is present: %s", e)
            raise e

    @overload
    async def put(
        self, session: AsyncSession, entity_id: int, new_entity: T
    ) -> bool: ...

    @overload
    async def put(
        self, session: AsyncSession, entity_id: list[int], new_entity: T
    ) -> bool: ...

    async def put(
        self, session: AsyncSession, entity_id: int | list[int], new_entity: T
    ) -> bool:
        """Updates an entity by its ID."""
        if isinstance(entity_id, list):
            return await self.__put_many(session, entity_id, new_entity)
        else:
            return await self.__put_one(session, entity_id, new_entity)

    async def __put_many(
        self, session: AsyncSession, entity_ids: list[int], new_entity: T
    ) -> bool:
        """Updates a list of entities."""
        statement = select(self.model_class).where(
            col(self.model_class.object_id).in_(entity_ids)
        )
        result = await session.execute(statement)
        old_entities = list(result.scalars().all())

        try:
            assert old_entities
            assert all(isinstance(entity.object_id, int) for entity in old_entities)
        except AssertionError as e:
            logger.error("Error updating entities: %s", e)
            raise ValueError("All entity IDs must be integers") from e

        for old_entity in old_entities:
            new_entity_data = new_entity.model_dump(
                exclude_unset=True, exclude_none=True
            )
            for key, value in new_entity_data.items():
                setattr(old_entity, key, value)
        session.add_all(old_entities)
        return True

    async def count(self, session: AsyncSession) -> int:
        """Counts the number of entities in the table."""
        return await self.__rows(session)

    async def __put_one(
        self, session: AsyncSession, entity_id: int, new_entity: T
    ) -> bool:
        """Updates an entity by its ID."""
        try:
            assert new_entity
            assert entity_id
            assert isinstance(entity_id, int)
        except AssertionError as e:
            logger.error("Error updating entity: %s", e)
            raise ValueError("Invalid entity") from e

        statement = select(self.model_class).where(
            self.model_class.object_id == entity_id
        )
        result = await session.execute(statement)
        entity = result.scalar_one_or_none()

        try:
            assert entity
            assert isinstance(entity, self.model_class)
        except AssertionError as e:
            raise EntityNotFoundError(entity_id) from e

        new_entity_data = new_entity.model_dump(exclude_unset=True, exclude_none=True)
        for key, value in new_entity_data.items():
            setattr(entity, key, value)
        session.add(entity)
        return True

    @overload
    async def pass_insert_checks(self, session: AsyncSession, entity: T) -> T: ...

    @overload
    async def pass_insert_checks(
        self, session: AsyncSession, entity: list[T]
    ) -> list[T]: ...

    async def pass_insert_checks(
        self, session: AsyncSession, entity: T | list[T]
    ) -> T | list[T]:
        """Private method. Checks if entities are exists in db and validates them."""
        try:
            if isinstance(entity, list):
                return await self.__insert_check_for_many(session, entity)
            else:
                return await self.__insert_check_for_one(session, entity)
        except EntityAlreadyExistsError as e:
            raise e
        except Exception as e:
            logger.error("Unknown error passing insert checks: %s", e)
            raise e

    async def __insert_check_for_many(
        self, session: AsyncSession, entities: list[T]
    ) -> list[T]:
        """Private method. Checks if entities are exists in db and validates them."""
        checked_entities: list[T] = []

        for entity in entities:
            try:
                entity = await self.__insert_check_for_one(session, entity)
            except EntityAlreadyExistsError:
                continue
            except Exception as e:
                logger.error("Unknown error passing insert checks: %s", e)
                raise e

            checked_entities.append(entity)

        try:
            assert len(checked_entities) > 0
        except AssertionError as e:
            logger.error("Error validating entities: %s", e)
            raise e

        return checked_entities

    async def __insert_check_for_one(self, session: AsyncSession, entity: T) -> T:
        """Private method. Checks if entity is exists in db and"""
        try:
            assert not await self.is_present(session, entity.object_id)
            entity = self.model_class.model_validate(entity)
        except AssertionError as e:
            raise EntityAlreadyExistsError(
                entity.object_id, self.model_class.__name__
            ) from e
        except ValidationError as e:
            logger.error("Failed to validate entity: %s", e)
            raise ValueError("Invalid entity") from e
        except Exception as e:
            logger.error("Unknown error adding entity: %s", e)
            raise e

        return entity

    async def __table_is_empty(self, session: AsyncSession) -> bool:
        """Private method. Checks if table is empty."""
        query = select(exists(select(self.model_class)))
        result = await session.execute(query)
        return result.scalar_one_or_none() is None

    async def __rows(self, session: AsyncSession) -> int:
        """Private method. Returns the number of rows in the table."""
        query = select(func.count()).select_from(self.model_class)
        result = await session.execute(query)
        response = result.scalar_one_or_none()
        try:
            assert response
            assert isinstance(response, int)
            assert response > 0

            return response
        except AssertionError as e:
            logger.error("Error getting rows: %s", e)
            return 0
