import logging
import os
from typing import cast

from google.auth import default as google_default_credentials  # type: ignore
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings

from src.shared.config import get_secret

logger = logging.getLogger("athena.telemetree.shared")


class TelemetreeConfig(BaseSettings):
    # GOOGLE CLOUD VARIABLES
    google_project_id: str | None = Field(None, validation_alias="GOOGLE_CLOUD_PROJECT")
    enterprise_token_secret_id: str | None = Field(
        None, validation_alias="TELEMETREE_ENTERPRISE_SECRET_ID"
    )

    class Config:
        env_prefix = "TELEMETREE_"
        extra = "ignore"
        env_file = ".env"

    @computed_field(return_type=str)  # type: ignore
    @property
    def enterprise_token(self) -> str:
        """Fetch enterprise token from Secret Manager or local environment."""
        if not self.enterprise_token_secret_id:
            local_enterprise_token = os.environ.get("TELEMETREE_ENTERPRISE_TOKEN")
            if local_enterprise_token:
                logger.warning(
                    "Using TELEMETREE_ENTERPRISE_TOKEN env var for local dev. "
                    "Set TELEMETREE_ENTERPRISE_SECRET_ID for deployed environments."
                )
                return local_enterprise_token
        if not self.google_project_id:
            # Auto-detect project ID
            try:
                _creds, detected_project_id = google_default_credentials()  # type: ignore
                if detected_project_id:
                    self.google_project_id = cast(str, detected_project_id)
                else:
                    raise ValueError("Could not auto-detect Google Cloud Project ID.")
            except Exception as e:
                raise ValueError(
                    f"Failed to get Google Cloud Project ID for secret fetching: {e}"
                ) from e
        logger.debug(
            f"Attempting to fetch secret '{self.enterprise_token_secret_id}' "
            f"from project '{self.google_project_id}'"
        )
        fetched_enterprise_token = get_secret(
            self.google_project_id,
            self.enterprise_token_secret_id,  # type: ignore
        )
        if fetched_enterprise_token is None:
            raise ValueError(
                "Failed to fetch enterprise token from Secret Manager "
                + f"(Secret ID: {self.enterprise_token_secret_id}). "
                + "Check logs and permissions."
            )
        return fetched_enterprise_token
