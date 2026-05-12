from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ApiResponse(BaseModel):
    code: int = 0
    data: Any = None
    msg: str = ""


def ok(data: Any = None) -> dict[str, Any]:
    return {"code": 0, "data": data, "msg": ""}


class LoginRequest(BaseModel):
    pin: str = Field(min_length=1)


class BinanceApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    label: str = "Binance Futures Testnet"
    env: Literal["testnet", "mainnet"] = "testnet"
    confirm_mainnet: bool = False


class OrderRequest(BaseModel):
    symbol: str
    side: Literal["long", "short"]
    action: Literal["open", "close"]
    type: Literal["LIMIT", "MARKET"] = "LIMIT"
    qty: Decimal
    price: Decimal | None = None
    post_only: bool = False
    leverage: int | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

class ChaseConfig(BaseModel):
    enabled: bool = False
    interval_sec: int = Field(default=5, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    on_expire: Literal["cancel", "market", "keep"] = "cancel"


class LaddersConfig(BaseModel):
    count: int = Field(default=1, ge=1, le=20)
    spacing_pct: Decimal = Decimal("0")
    distribution: Literal["equal"] = "equal"


class FloatingOrderRequest(BaseModel):
    symbol: str
    side: Literal["long", "short"]
    action: Literal["open", "close"]
    float_pct: Decimal = Decimal("0")
    qty_mode: Literal["usdt", "base"] = "usdt"
    qty: Decimal
    chase: ChaseConfig = Field(default_factory=ChaseConfig)
    ladders: LaddersConfig = Field(default_factory=LaddersConfig)
    tp_pct: Decimal | None = None
    sl_pct: Decimal | None = None
    reduce_only: bool = False
    post_only: bool = True
    leverage: int | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

class ReverseRequest(BaseModel):
    symbol: str
    pin: str = Field(min_length=1)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class ProtectionRequest(BaseModel):
    fill_qty: Decimal
    avg_price: Decimal


class ConfirmPinRequest(BaseModel):
    pin: str = Field(min_length=1)


class SymbolFilterView(BaseModel):
    symbol: str
    tick_size: str
    step_size: str
    min_notional: str


class MonitorRuleRequest(BaseModel):
    name: str = Field(min_length=1)
    symbol: str
    metric: Literal["quote_volume", "price_change_pct", "last_price"]
    operator: Literal[">", ">=", "<", "<="]
    threshold: Decimal
    window: str = "5m"
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class MonitorEvaluateRequest(BaseModel):
    metric_values: dict[str, Decimal]


class StrategyRequest(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["grid", "ma_cross", "ai_signal"]
    symbol: str
    params: dict[str, Any] = Field(default_factory=dict)
    stoploss_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class StrategyRunOnceRequest(BaseModel):
    execute: bool = False
    pin: str | None = None


class AiTradeDraftRequest(BaseModel):
    symbol: str
    action: Literal["long_open", "short_open", "close", "hold"]
    confidence: Decimal = Decimal("0")
    rationale: str = ""
    suggested_order: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class AiAnalyzeRequest(BaseModel):
    symbol: str
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class AiDraftApproveRequest(BaseModel):
    pin: str = Field(min_length=1)
    execute: bool = False
