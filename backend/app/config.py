from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BACKEND_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "oakproof-backend"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    storage_root: Path = Path("data")
    cors_allow_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    capture_signer_allowlist: str = ""
    flare_rpc_url: str = "https://coston2-api.flare.network/ext/C/rpc"
    flare_chain_id: int = 114
    flare_explorer_base_url: str = "https://coston2-explorer.flare.network"
    anchor_contract_address: str = ""
    anchor_private_key: str | None = None
    anchor_gas_limit: int = 350_000
    anchor_timeout_seconds: int = 180

    @property
    def origins(self) -> list[str]:
        if self.cors_allow_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def allowed_signers(self) -> set[str]:
        return {
            signer.strip().lower()
            for signer in self.capture_signer_allowlist.split(",")
            if signer.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
