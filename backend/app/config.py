from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'app.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    binance_env: str = "testnet"
    app_host: str = "127.0.0.1"
    app_port: int = 18080

    session_secret: str = ""
    app_pin: str = ""
    app_pin_hash: str = ""

    database_url: str = DEFAULT_DATABASE_URL

    binance_rest_base: str = "https://demo-fapi.binance.com"
    binance_ws_base: str = "wss://stream.binancefuture.com/ws"
    binance_recv_window: int = 5000
    binance_api_key: str = ""
    binance_api_secret: str = ""

    per_order_max_usdt: str = "500"
    global_max_position_usdt: str = "5000"
    global_max_leverage: int = 10
    allowed_symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"
    forbidden_symbols: str = ""

    confirm_mainnet: bool = Field(default=False)

    monitor_scheduler_enabled: bool = False
    monitor_scheduler_interval_sec: int = 30
    strategy_scheduler_enabled: bool = False
    strategy_scheduler_interval_sec: int = 60
    strategy_scheduler_execute: bool = False
    user_stream_enabled: bool = False
    user_stream_keepalive_sec: int = 30 * 60
    worker_error_sleep_sec: int = 5

    ai_provider: str = "mock"
    ai_min_confidence: str = "0.65"
    ai_default_qty_usdt: str = "50"
    ai_default_tp_pct: str = "0.5"
    ai_default_sl_pct: str = "0.3"

    @property
    def is_mainnet(self) -> bool:
        return self.binance_env.lower() == "mainnet"

    @property
    def allowed_symbol_set(self) -> set[str]:
        return {s.strip().upper() for s in self.allowed_symbols.split(",") if s.strip()}

    @property
    def forbidden_symbol_set(self) -> set[str]:
        return {s.strip().upper() for s in self.forbidden_symbols.split(",") if s.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
