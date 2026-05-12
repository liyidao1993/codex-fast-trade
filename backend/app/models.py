from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SystemState(Base):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    env: Mapped[str] = mapped_column(String(30), default="testnet")
    key_encrypted: Mapped[str] = mapped_column(Text, default="")
    secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    label: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    exchange_order_id: Mapped[str] = mapped_column(String(80), default="")
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    side: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(10))
    exchange_side: Mapped[str] = mapped_column(String(10))
    position_side: Mapped[str] = mapped_column(String(10), default="BOTH")
    order_type: Mapped[str] = mapped_column(String(30))
    price: Mapped[str] = mapped_column(String(80), default="")
    qty: Mapped[str] = mapped_column(String(80))
    executed_qty: Mapped[str] = mapped_column(String(80), default="0")
    avg_price: Mapped[str] = mapped_column(String(80), default="0")
    status: Mapped[str] = mapped_column(String(30), default="LOCAL_NEW")
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    strategy_run_id: Mapped[str] = mapped_column(String(80), default="")
    parent_order_id: Mapped[str] = mapped_column(String(80), default="")
    tp_pct: Mapped[str] = mapped_column(String(80), default="")
    sl_pct: Mapped[str] = mapped_column(String(80), default="")
    protection_status: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProtectionOrder(Base):
    __tablename__ = "protection_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_client_order_id: Mapped[str] = mapped_column(String(80), index=True)
    sl_client_order_id: Mapped[str] = mapped_column(String(80), default="")
    sl_exchange_order_id: Mapped[str] = mapped_column(String(80), default="")
    tp_client_order_id: Mapped[str] = mapped_column(String(80), default="")
    tp_exchange_order_id: Mapped[str] = mapped_column(String(80), default="")
    sl_status: Mapped[str] = mapped_column(String(40), default="")
    tp_status: Mapped[str] = mapped_column(String(40), default="")
    sl_price: Mapped[str] = mapped_column(String(80), default="")
    tp_price: Mapped[str] = mapped_column(String(80), default="")
    mode: Mapped[str] = mapped_column(String(30), default="pct")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GuardRules(Base):
    __tablename__ = "guard_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    per_order_max_usdt: Mapped[str] = mapped_column(String(80), default="500")
    global_max_position_usdt: Mapped[str] = mapped_column(String(80), default="5000")
    global_max_leverage: Mapped[int] = mapped_column(Integer, default=10)
    allowed_symbols: Mapped[str] = mapped_column(Text, default="BTCUSDT,ETHUSDT,SOLUSDT")
    forbidden_symbols: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MonitorRule(Base):
    __tablename__ = "monitor_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    metric: Mapped[str] = mapped_column(String(40))
    operator: Mapped[str] = mapped_column(String(10))
    threshold: Mapped[str] = mapped_column(String(80))
    window: Mapped[str] = mapped_column(String(20), default="5m")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MonitorEvent(Base):
    __tablename__ = "monitor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(80))
    threshold: Mapped[str] = mapped_column(String(80))
    triggered: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(80), default="")
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="new")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(40))
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    params: Mapped[str] = mapped_column(Text, default="{}")
    stoploss_config: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(30), default="created")
    last_heartbeat: Mapped[str] = mapped_column(String(80), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AiTradeDraft(Base):
    __tablename__ = "ai_trade_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    action: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(40), default="0")
    rationale: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
