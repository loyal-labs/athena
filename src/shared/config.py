import logging
from typing import Literal, TypeVar

from pydantic import BaseModel, Field, computed_field
from sqlalchemy.engine import URL

from src.shared.secrets import OnePasswordManager

"""
TYPE VARIABLES
"""

R = TypeVar("R")

"""
LOGGING
"""

logger = logging.getLogger("athena.settings")


class PostgresConfig(BaseModel):
    """PostgreSQL configuration, handles App Engine Unix sockets."""

    # secrets management
    one_password_vault: str = "Variables"
    one_password_field_name: str = "ATHENA_DATABASE"

    # Basic config
    user: str = Field("postgres")
    host: str = Field("localhost")
    port: int = Field(5432)
    db_name: str = Field("deus-vult")
    password: str = Field(..., description="Password for the database")

    def _build_sqlalchemy_url(self, use_placeholder_password: bool = False) -> URL:
        """Internal helper to construct the SQLAlchemy URL object."""
        password_to_use = "XXXXXX" if use_placeholder_password else self.password

        sqlalchemy_url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=password_to_use,  # Use determined password
            host=self.host,
            port=self.port,
            database=self.db_name,
        )
        return sqlalchemy_url

    # --- Public Properties ---
    @property
    def db_url(self) -> str:
        """Generates the appropriate SQLAlchemy database URL with the real password."""
        url_obj = self._build_sqlalchemy_url(use_placeholder_password=False)
        return url_obj.render_as_string(hide_password=False)

    @property
    def safe_db_url(self) -> str:
        """Generates a database URL safe for logging (password hidden)."""
        url_obj = self._build_sqlalchemy_url(use_placeholder_password=True)
        return url_obj.render_as_string(hide_password=False)
