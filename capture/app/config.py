from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_VERIFICATION_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "anti_replay_thresholds.json"
)


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
    backend_base_url: str | None = "http://127.0.0.1:8000"
    cors_allow_origins: str = "*"
    station_id: str = "oak4-station"
    station_signer_private_key: str | None = None
    simulate: bool = True
    oak_device_id: str | None = None
    auto_submit_to_backend: bool = True
    receipt_namespace: str = "oakproof"
    request_timeout_seconds: float = 20.0
    verification_config_path: Path = Field(default=DEFAULT_VERIFICATION_CONFIG_PATH)
    runtime_fps: float = 20.0
    runtime_rgb_width: int = 1280
    runtime_rgb_height: int = 960
    runtime_stereo_width: int = 1280
    runtime_stereo_height: int = 800
    runtime_sync_threshold_ms: int = 50
    session_start_timeout_seconds: float = 10.0
    session_stop_timeout_seconds: float = 20.0

    @field_validator("oak_device_id", mode="before")
    @classmethod
    def blank_oak_device_id_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def origins(self) -> list[str]:
        if self.cors_allow_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
