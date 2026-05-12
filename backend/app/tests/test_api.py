import os
import uuid

os.environ["APP_PIN"] = "123456"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AiTradeDraft, Alert, Order  # noqa: E402


def test_health_and_ready() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json()["data"]["status"] == "ok"
        assert client.get("/readyz").json()["data"]["status"] == "ready"


def test_login_and_logout() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        bad = client.post("/api/v1/auth/login", json={"pin": "wrong"})
        assert bad.status_code == 401

        good = client.post("/api/v1/auth/login", json={"pin": "123456"})
        assert good.status_code == 200
        assert good.json()["data"]["authenticated"] is True
        assert "cft_session" in good.cookies

        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        assert logout.json()["data"]["authenticated"] is False


def test_positions_requires_login() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/positions")
        assert response.status_code == 401


def test_destructive_order_actions_require_pin_after_login() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200

        close_response = client.post("/api/v1/orders/close-all", json={"pin": "wrong"})
        assert close_response.status_code == 401

        reverse_response = client.post("/api/v1/orders/reverse", json={"symbol": "BTCUSDT", "pin": "wrong"})
        assert reverse_response.status_code == 401


async def seed_order_for_api_test() -> str:
    client_order_id = f"co-api-cancel-{uuid.uuid4().hex[:12]}"
    async with SessionLocal() as session:
        order = Order(
            client_order_id=client_order_id,
            exchange_order_id="1",
            symbol="BTCUSDT",
            side="long",
            action="open",
            exchange_side="BUY",
            position_side="BOTH",
            order_type="LIMIT",
            price="100",
            qty="1",
            status="NEW",
        )
        session.add(order)
        await session.commit()
        return order.client_order_id


async def seed_alert_for_api_test() -> int:
    async with SessionLocal() as session:
        alert = Alert(
            source="monitor",
            source_id="1",
            symbol="BTCUSDT",
            level="warning",
            title="BTC volume triggered",
            message="2000000 > 1000000",
        )
        session.add(alert)
        await session.commit()
        return alert.id


async def seed_ai_draft_for_api_test() -> int:
    async with SessionLocal() as session:
        draft = AiTradeDraft(
            symbol="BTCUSDT",
            action="long_open",
            confidence="0.8",
            rationale="test",
            payload='{"qty_mode":"usdt","qty":"50","float_pct":"-0.05","tp_pct":"0.5","sl_pct":"0.3"}',
            status="draft",
        )
        session.add(draft)
        await session.commit()
        return draft.id


def test_cancel_order_requires_second_pin_after_login() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200
        client_order_id = client.portal.call(seed_order_for_api_test)
        response = client.request("DELETE", f"/api/v1/orders/{client_order_id}", json={"pin": "wrong"})
        assert response.status_code == 401


def test_alert_ack_after_login() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200
        alert_id = client.portal.call(seed_alert_for_api_test)
        response = client.post(f"/api/v1/monitors/alerts/{alert_id}/ack")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "acked"

    async def load_status() -> str:
        async with SessionLocal() as session:
            alert = await session.scalar(select(Alert).where(Alert.id == alert_id))
            assert alert is not None
            return alert.status

    with TestClient(app) as client:
        assert client.portal.call(load_status) == "acked"


def test_ai_draft_validate_and_approve_require_pin() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200
        draft_id = client.portal.call(seed_ai_draft_for_api_test)
        validate_response = client.post(f"/api/v1/ai/drafts/{draft_id}/validate")
        assert validate_response.status_code == 200
        assert validate_response.json()["data"]["status"] == "validated"

        bad_pin = client.post(f"/api/v1/ai/drafts/{draft_id}/approve", json={"pin": "wrong", "execute": False})
        assert bad_pin.status_code == 401

        good_pin = client.post(f"/api/v1/ai/drafts/{draft_id}/approve", json={"pin": "123456", "execute": False})
        assert good_pin.status_code == 200
        assert good_pin.json()["data"]["status"] == "approved"


def test_binance_key_settings_roundtrip() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.get("/api/v1/settings/binance-key").status_code == 401
        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200
        assert client.delete("/api/v1/settings/binance-key").status_code == 200

        empty = client.get("/api/v1/settings/binance-key")
        assert empty.status_code == 200
        missing_test = client.post("/api/v1/settings/binance-key/test")
        assert missing_test.status_code == 400

        saved = client.put(
            "/api/v1/settings/binance-key",
            json={"api_key": "test-key-123456", "api_secret": "test-secret-abcdef", "label": "Testnet"},
        )
        assert saved.status_code == 200
        data = saved.json()["data"]
        assert data["configured"] is True
        assert data["key_masked"] == "test...3456"
        assert "secret" not in data

        deleted = client.delete("/api/v1/settings/binance-key")
        assert deleted.status_code == 200
        assert deleted.json()["data"]["configured"] is False


def test_worker_status_requires_login_and_returns_snapshot() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.get("/api/v1/workers/status").status_code == 401
        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200
        response = client.get("/api/v1/workers/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["monitor"]["enabled"] is False
        assert data["strategy"]["enabled"] is False
        assert data["user_stream"]["enabled"] is False


def test_activity_endpoints_require_login_and_return_lists() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.get("/api/v1/orders").status_code == 401
        assert client.get("/api/v1/orders/events").status_code == 401
        assert client.get("/api/v1/orders/protections").status_code == 401
        assert client.get("/api/v1/monitors/alerts").status_code == 401
        assert client.get("/api/v1/monitors/events").status_code == 401
        assert client.get("/api/v1/strategies/runs").status_code == 401
        assert client.get("/api/v1/activity/recent").status_code == 401

        assert client.post("/api/v1/auth/login", json={"pin": "123456"}).status_code == 200
        for path in (
            "/api/v1/orders",
            "/api/v1/orders/events",
            "/api/v1/orders/protections",
            "/api/v1/monitors/alerts",
            "/api/v1/monitors/events",
            "/api/v1/strategies/runs",
            "/api/v1/activity/recent",
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert isinstance(response.json()["data"], list)
