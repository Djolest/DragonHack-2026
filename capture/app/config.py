from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CAPTURE_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "oakproof-capture"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8100
    log_level: str = "INFO"
    storage_root: Path = Path("data")
    public_base_url: str = "http://127.0.0.1:8100"
    backend_base_url: str = "http://127.0.0.1:8000"
    cors_allow_origins: str = "*"
    station_id: str = "oakproof-station-01"
    station_signer_private_key: str = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    simulate: bool = True
    oak_device_id: str | None = None
    auto_submit_to_backend: bool = True
    receipt_namespace: str = "oakproof"
    request_timeout_seconds: float = 10.0

    @property
    def origins(self) -> list[str]:
        if self.cors_allow_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
