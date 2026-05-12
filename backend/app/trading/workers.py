import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.exchanges.binance import BinanceClient
from app.exchanges.credentials import load_binance_client
from app.models import MonitorRule, Strategy, StrategyRun
from app.strategies.runner import run_strategy_once
from app.trading.monitoring import evaluate_rule_with_live_ticker
from app.trading.user_stream import UserStreamState, consume_user_stream


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CycleResult:
    scanned: int = 0
    succeeded: int = 0
    failed: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkerState:
    name: str
    enabled: bool
    running: bool = False
    iterations: int = 0
    last_ok: str = ""
    last_error: str = ""
    last_event: str = ""
    task: asyncio.Task | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "running": self.running,
            "iterations": self.iterations,
            "last_ok": self.last_ok,
            "last_error": self.last_error,
            "last_event": self.last_event,
        }


async def run_monitor_cycle(session: AsyncSession, client: BinanceClient | None = None) -> CycleResult:
    client = client or await load_binance_client(session)
    rules = list(
        (
            await session.scalars(
                select(MonitorRule).where(MonitorRule.enabled == 1).order_by(MonitorRule.id.asc())
            )
        ).all()
    )
    result = CycleResult(scanned=len(rules))
    for rule in rules:
        try:
            event = await evaluate_rule_with_live_ticker(session=session, rule=rule, client=client)
            result.succeeded += 1
            result.details.append({"rule_id": rule.id, "event_id": event.id, "triggered": bool(event.triggered)})
        except Exception as exc:
            result.failed += 1
            result.details.append({"rule_id": rule.id, "error": str(exc)})
    return result


async def run_strategy_cycle(
    session: AsyncSession,
    *,
    execute: bool = False,
    client: BinanceClient | None = None,
) -> CycleResult:
    client = client or await load_binance_client(session)
    strategies = list(
        (
            await session.scalars(
                select(Strategy).where(Strategy.enabled == 1).order_by(Strategy.id.asc())
            )
        ).all()
    )
    result = CycleResult(scanned=len(strategies))
    for strategy in strategies:
        run = StrategyRun(strategy_id=strategy.id, status="running", last_heartbeat=utc_now())
        session.add(run)
        await session.commit()
        try:
            signal = await run_strategy_once(session=session, strategy=strategy, execute=execute, client=client)
            run.status = "executed" if signal.get("executed") else str(signal.get("signal", "done"))
            run.last_heartbeat = utc_now()
            await session.commit()
            result.succeeded += 1
            result.details.append({"strategy_id": strategy.id, "run_id": run.id, "result": signal})
        except Exception as exc:
            run.status = "error"
            run.error = str(exc)
            run.last_heartbeat = utc_now()
            await session.commit()
            result.failed += 1
            result.details.append({"strategy_id": strategy.id, "run_id": run.id, "error": str(exc)})
    return result


class BackgroundSupervisor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.states = {
            "monitor": WorkerState("monitor", self.settings.monitor_scheduler_enabled),
            "strategy": WorkerState("strategy", self.settings.strategy_scheduler_enabled),
            "user_stream": WorkerState("user_stream", self.settings.user_stream_enabled),
        }
        self.user_stream_state = UserStreamState()

    async def start(self) -> None:
        await self._start_loop(
            "monitor",
            interval_sec=self.settings.monitor_scheduler_interval_sec,
            cycle=self._monitor_cycle,
        )
        await self._start_loop(
            "strategy",
            interval_sec=self.settings.strategy_scheduler_interval_sec,
            cycle=self._strategy_cycle,
        )
        state = self.states["user_stream"]
        if state.enabled and state.task is None:
            state.task = asyncio.create_task(self._user_stream_loop(state))

    async def stop(self) -> None:
        tasks = [state.task for state in self.states.values() if state.task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        for state in self.states.values():
            state.running = False
            state.task = None

    def snapshot(self) -> dict[str, Any]:
        data = {name: state.snapshot() for name, state in self.states.items()}
        data["user_stream"]["listen_key"] = bool(self.user_stream_state.listen_key)
        data["user_stream"]["events_handled"] = self.user_stream_state.events_handled
        data["user_stream"]["keepalives"] = self.user_stream_state.keepalives
        return data

    async def _start_loop(self, name: str, *, interval_sec: int, cycle: Callable[[], Awaitable[CycleResult]]) -> None:
        state = self.states[name]
        if state.enabled and state.task is None:
            state.task = asyncio.create_task(self._periodic_loop(state, interval_sec=max(interval_sec, 1), cycle=cycle))

    async def _periodic_loop(
        self,
        state: WorkerState,
        *,
        interval_sec: int,
        cycle: Callable[[], Awaitable[CycleResult]],
    ) -> None:
        state.running = True
        try:
            while True:
                try:
                    result = await cycle()
                    state.iterations += 1
                    state.last_ok = utc_now()
                    state.last_event = f"scanned={result.scanned}, ok={result.succeeded}, failed={result.failed}"
                    if result.failed:
                        state.last_error = str(result.details[-1])
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    state.last_error = str(exc)
                    await asyncio.sleep(max(self.settings.worker_error_sleep_sec, 1))
                await asyncio.sleep(interval_sec)
        finally:
            state.running = False

    async def _monitor_cycle(self) -> CycleResult:
        async with SessionLocal() as session:
            return await run_monitor_cycle(session)

    async def _strategy_cycle(self) -> CycleResult:
        async with SessionLocal() as session:
            return await run_strategy_cycle(session, execute=self.settings.strategy_scheduler_execute)

    async def _user_stream_loop(self, state: WorkerState) -> None:
        state.running = True
        while True:
            try:
                async with SessionLocal() as session:
                    client = await load_binance_client(session)
                await consume_user_stream(
                    state=self.user_stream_state,
                    session_factory=SessionLocal,
                    client=client,
                    keepalive_sec=self.settings.user_stream_keepalive_sec,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.last_error = str(exc)
                await asyncio.sleep(max(self.settings.worker_error_sleep_sec, 1))
            finally:
                state.iterations += 1
                state.last_ok = utc_now()


background_supervisor = BackgroundSupervisor()
