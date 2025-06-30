import asyncio
import hashlib
import inspect
import logging
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast

import orjson
from diskcache import Cache  # type: ignore

logger = logging.getLogger("athena.cache")

# Type variables for better type safety
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])

# Global cache instance
_cache_instance = None


def get_disk_cache() -> Cache:
    """Get or create the disk cache instance."""
    global _cache_instance
    if _cache_instance is None:
        # Explicitly use the /tmp directory which is usually writable

        cache_dir = Path("/tmp/.cache")
        logger.info("Using cache directory: %s", cache_dir)

        # Ensure cache directory exists
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Successfully created or found cache directory: %s", cache_dir)
        except OSError as e:
            # Log a more specific error if even /tmp/.cache fails
            logger.error(
                "Failed to create cache directory %s: %s", cache_dir, e, exc_info=True
            )
            raise  # Re-raise the exception as caching won't work

        _cache_instance = Cache(str(cache_dir))
        assert _cache_instance is not None, "Failed to create disk cache instance"
        logger.info("Disk cache instance created successfully.")
    return _cache_instance


def serialize_value(value: Any) -> bytes:
    """Serialize a value to bytes for caching, ensuring dict structure for objects."""
    try:
        # Helper to convert items to JSON-serializable dicts/primitives
        def prep_for_orjson(item: Any) -> Any:
            if hasattr(item, "model_dump"):
                return item.model_dump_json()
            elif hasattr(item, "dict"):
                return item.dict()
            elif isinstance(item, dict | list | str | int | float | bool | type(None)):
                return item  # type: ignore
            else:
                # Cannot serialize this type reliably into a dict/primitive
                logger.error(
                    f"Cannot serialize type {type(item)} for caching. "
                    "Ensure it has .model_dump() or add handling."
                )
                raise TypeError(
                    f"Unsupported type for cache serialization: {type(item)}"
                )

        # Prepare the main value (list or single item)
        if isinstance(value, list):
            # Create the list of dictionaries/primitives
            serializable_data = [prep_for_orjson(item) for item in value]  # type: ignore
        else:
            # Prepare the single item
            serializable_data = prep_for_orjson(value)

        # Single call to orjson.dumps on the final structure
        result = orjson.dumps(serializable_data)
        assert isinstance(result, bytes), (
            f"orjson.dumps did not produce bytes, got {type(result)}"
        )
        return result

    except TypeError as e:  # Catch TypeErrors from prep_for_orjson or dumps
        logger.error(
            "Cache serialization failed: %s. Value type: %s.",
            e,
            type(value),  # type: ignore
            exc_info=True,
        )
        raise  # Re-raise the TypeError to prevent caching bad data
    except Exception as e:
        logger.error("Unexpected cache serialization error: %s", e, exc_info=True)
        raise


def deserialize_value(value: Any) -> Any:
    """
    Deserialize a value from bytes stored by diskcache.
    Handles both correctly serialized (list[dict]) and legacy
    double-serialized (list[str] where str is JSON) cache entries.
    """
    if value is None:
        logger.debug("Deserializing None value.")
        return None

    if not isinstance(value, bytes | bytearray):
        logger.warning(
            f"Deserialize_value received unexpected type: {type(value)}. "
            "Returning as is."
        )
        return value

    try:
        # First load: Get the structure stored
        loaded_data = orjson.loads(value)

        # --- Handle list case ---
        if isinstance(loaded_data, list):
            logger.debug(
                f"Initial load resulted in a list (length: {len(loaded_data)}). "  # type: ignore
                "Checking elements."
            )
            processed_list: list[dict[str, Any]] = []

            if loaded_data and isinstance(loaded_data[0], str):
                try:
                    # Test if the first element is JSON string
                    orjson.loads(loaded_data[0])
                    logger.debug(
                        "Detected list of JSON strings (double-serialized). "
                        "Performing second load."
                    )
                    processed_list = []
                    for item_str in loaded_data:  # type: ignore
                        if isinstance(item_str, str):
                            try:
                                processed_list.append(orjson.loads(item_str))
                            except Exception:
                                pass  # Handle inner parse error
                    return processed_list
                except orjson.JSONDecodeError:
                    logger.debug("List contains non-JSON strings.")
                    return loaded_data  # type: ignore
            # --- Handle String Case (Potential single double-serialized object) ---
        elif isinstance(loaded_data, str):
            logger.debug("Initial load resulted in a string. Checking if it's JSON.")
            try:
                # Second load: Attempt to parse the string as JSON
                inner_data = orjson.loads(loaded_data)
                logger.debug("Successfully parsed inner JSON string.")
                return inner_data  # Return the actual dict/list/primitive
            except orjson.JSONDecodeError:
                # It was just a plain string, not JSON
                logger.debug("String is not valid JSON. Returning string as is.")
                return loaded_data  # Return the original string
        else:
            logger.debug("Data appears as list of dicts/primitives.")
            return loaded_data  # type: ignore

    except orjson.JSONDecodeError as e:
        logger.error(
            f"Cache Deserialization Error (Outer Load): "
            f"Invalid JSON detected. Error: {e}",
            exc_info=True,
        )
        logger.error("Problematic cache bytes (prefix): %s", value[:100])
        return None
    except Exception as e:
        logger.error("Unexpected Cache Deserialization Error: %s", e, exc_info=True)
        return None


def generate_cache_key(
    func: Callable[..., Any],
    key_params: list[str] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """
    Generate a cache key based on the function and specified key parameters.

    Args:
        func: The function being called.
        key_params: A list of parameter names (potentially nested using '.')
                    to include in the cache key. If None or empty, only the
                    function name is used.
        args: Positional arguments passed to the function.
        kwargs: Keyword arguments passed to the function.

    Returns:
        A unique string cache key.

    Raises:
        KeyError: If a specified key_param is not found in the function arguments.
        AttributeError: If a nested attribute in a key_param path doesn't exist.
    """
    # Base key includes module and function name
    base_key_parts = [func.__module__, func.__name__]

    if not key_params:  # Handle None or empty list
        return ":".join(base_key_parts)

    # --- Combine args and kwargs into a single arguments dictionary ---
    try:
        sig = inspect.signature(func)  # type: ignore
        bound_args = sig.bind(*args, **kwargs)  # type: ignore
        bound_args.apply_defaults()  # type: ignore
        all_args = bound_args.arguments  # type: ignore
    except TypeError as e:
        logger.error(
            f"Failed to bind arguments for {func.__name__}: {e}. "
            + "Caching might be unreliable."
        )
        # Fallback: Use only kwargs (less robust but might work for simple cases)
        all_args = kwargs.copy()

    # --- Process specified key parameters ---
    param_key_parts: list[str] = []
    # Sort keys for consistent key generation
    sorted_key_params = sorted(key_params)  # type: ignore

    for param_name in sorted_key_params:
        try:
            # Handle potential nesting
            if "." in param_name:
                first_part, *rest_parts = param_name.split(".", 1)
                if first_part not in all_args:
                    raise KeyError(
                        f"Base parameter '{first_part}' for nested key '{param_name}' "
                        + "not found in function arguments."
                    )
                base_obj = all_args[first_part]  # type: ignore
                param_value = (  # type: ignore
                    _get_nested_attr(base_obj, rest_parts[0])
                    if rest_parts
                    else base_obj
                )
            else:
                # Simple parameter name
                if param_name not in all_args:
                    raise KeyError(
                        f"Parameter '{param_name}' not found in function arguments."
                    )
                param_value = all_args[param_name]  # type: ignore

            # Serialize/hash the parameter value for the key
            if param_value is None:
                param_hash = "None"
            elif hasattr(param_value, "model_dump"):  # type: ignore
                param_hash = hashlib.md5(
                    orjson.dumps(param_value.model_dump_json())  # type: ignore
                ).hexdigest()
            elif hasattr(param_value, "dict"):  # type: ignore
                param_hash = hashlib.md5(orjson.dumps(param_value.dict())).hexdigest()  # type: ignore
            elif isinstance(param_value, str | int | float | bool):
                param_hash = str(param_value)
            else:
                try:
                    param_hash = hashlib.md5(orjson.dumps(param_value)).hexdigest()
                except TypeError:
                    logger.warning(
                        "Value for param '%s' (type: %s) "
                        + "is not directly ORJSON serializable. "
                        + "Hashing string representation.",
                        param_name,
                        type(param_value),  # type: ignore
                    )
                    param_hash = hashlib.md5(str(param_value).encode()).hexdigest()  # type: ignore

            param_key_parts.append(f"{param_name}={param_hash}")

        except (KeyError, AttributeError) as e:
            logger.error(
                f"Error accessing parameter '{param_name}' for cache key generation in "
                + f"{func.__name__}: {e}"
            )
            # Raise the error to prevent caching with an incomplete/incorrect key
            raise ValueError(
                f"Failed to generate cache key component for '{param_name}': {e}"
            ) from e
        except Exception as e:
            logger.error(
                f"Unexpected error processing parameter '{param_name}' "
                + f"for cache key in {func.__name__}: {e}",
                exc_info=True,
            )
            raise ValueError(
                "Unexpected error generating cache key component for "
                + f"'{param_name}': {e}"
            ) from e

    # Combine base key and parameter parts
    full_key = ":".join(base_key_parts + param_key_parts)
    logger.debug("Generated cache key for %s: %s", func.__name__, full_key)
    return full_key


def _get_nested_attr(obj: Any, attr_path: str) -> Any:
    """Safely retrieve a nested attribute using dot notation."""
    attributes = attr_path.split(".")
    current_obj = obj
    for attribute in attributes:
        if isinstance(current_obj, dict):
            if attribute not in current_obj:
                raise KeyError(f"Key '{attribute}' not found in dict.")
            current_obj = current_obj[attribute]  # type: ignore
        else:
            if not hasattr(current_obj, attribute):  # type: ignore
                raise AttributeError(
                    f"Object of type {type(current_obj)} has no attribute '{attribute}'"  # type: ignore
                )
            current_obj = getattr(current_obj, attribute)  # type: ignore
    return current_obj  # type: ignore


def disk_cache(
    key_params: list[str] | None = None,
    ttl: int = 3600,
) -> Callable[[F], F]:
    """
    Cache decorator using diskcache, supporting multiple key parameters.

    Args:
        key_params: A list of parameter names (potentially nested using '.')
                    to include in the cache key. If None or empty, only the
                    function name/module is used. Order doesn't matter.
        ttl: Time to live for cache entries in seconds.

    Returns:
        Decorated function with caching.

    Raises:
        ValueError: If key generation fails due to missing parameters or attributes.
    """
    if ttl <= 0:
        raise ValueError("Cache TTL must be positive")

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                # Generate the key using args and kwargs
                cache_key = generate_cache_key(
                    func, key_params, args, kwargs
                )  # Pass args/kwargs
                cache = get_disk_cache()

                # --- Cache Read ---
                cached_data = cache.get(cache_key)  # type: ignore
                if cached_data is not None:
                    logger.debug("Cache hit for key: %s", cache_key)
                    try:
                        deserialized_result = deserialize_value(cached_data)
                        return deserialized_result
                    except Exception as deser_err:
                        logger.error(
                            "Cache deserialization error for key %s: %s. "
                            "Fetching fresh data.",
                            cache_key,
                            deser_err,
                            exc_info=True,
                        )
                        # Proceed to fetch fresh data if deserialization fails
                else:
                    logger.debug("Cache miss for key: %s", cache_key)

                # --- Cache Miss: Execute function ---
                result = await func(*args, **kwargs)

                # --- Cache Write ---
                try:
                    serialized_result = serialize_value(result)
                    if not cache.set(cache_key, serialized_result, expire=ttl):  # type: ignore
                        logger.warning("Failed to set cache for key: %s", cache_key)
                except Exception as ser_err:
                    logger.error(
                        "Cache serialization error for key %s: %s. Result not cached.",
                        cache_key,
                        ser_err,
                        exc_info=True,
                    )
                    # Return the result even if caching fails

                return result

            except ValueError as key_err:
                # Error during key generation (missing param) - do not cache
                logger.error(
                    f"Cache key generation failed for {func.__name__}: {key_err}. "
                    + "Skipping cache.",
                    exc_info=True,
                )
                return await func(*args, **kwargs)
            except Exception as e:
                # Catch unexpected errors during cache interaction
                logger.error(
                    f"Unexpected caching error for async {func.__name__}: {e}. "
                    + "Falling back.",
                    exc_info=True,
                )
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # --- Sync version: Logic mirrors async_wrapper ---
            try:
                cache_key = generate_cache_key(func, key_params, args, kwargs)
                cache = get_disk_cache()

                # Cache Read
                cached_data = cache.get(cache_key)  # type: ignore
                if cached_data is not None:
                    logger.debug("Cache hit for key: %s", cache_key)
                    try:
                        return deserialize_value(cached_data)
                    except Exception as deser_err:
                        logger.error(
                            f"Cache deserialization error for key {cache_key}: "
                            + f"{deser_err}. Fetching fresh data.",
                            exc_info=True,
                        )
                else:
                    logger.debug("Cache miss for key: %s", cache_key)

                # Cache Miss
                result = func(*args, **kwargs)

                # Cache Write
                try:
                    serialized_result = serialize_value(result)
                    if not cache.set(cache_key, serialized_result, expire=ttl):  # type: ignore
                        logger.warning("Failed to set cache for key: %s", cache_key)
                except Exception as ser_err:
                    logger.error(
                        "Cache serialization error for key %s: %s. Result not cached.",
                        cache_key,
                        ser_err,
                        exc_info=True,
                    )

                return result

            except ValueError as key_err:
                logger.error(
                    "Cache key generation failed for %s: %s. Skipping cache.",
                    func.__name__,
                    key_err,
                    exc_info=True,
                )
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    "Unexpected caching error for sync %s: %s. Falling back.",
                    func.__name__,
                    e,
                    exc_info=True,
                )
                return func(*args, **kwargs)

        # Return the appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    return decorator
