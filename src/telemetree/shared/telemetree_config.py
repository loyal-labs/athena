from pydantic import Field
from pydantic_settings import BaseSettings


class TelemetreeConfig(BaseSettings):
    enterprise_token: str = Field(..., validation_alias="TELEMETREE_ENTERPRISE_TOKEN")

    class Config:
        env_prefix = "TELEMETREE_"
        extra = "ignore"
        env_file = ".env"
