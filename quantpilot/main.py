"""QUANT PILOT API: REST + WebSocket streaming of live agent events.

Run:  python -m uvicorn backend.main:app --port 8000
Educational use only. Not financial advice. Trading involves risk of loss.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .agents import PIPELINE_ORDER
from .config import CONFIRM_PHRASE, INSTRUMENTS, settings
from .core.backtest import run_backtest
from .core.events import EventHub
from .core.indicators import session_info
from .core.orchestrator import Orchestrator, Services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("quantpilot.api")

hub = EventHub()
services: Optional[Services] = None
orchestrator: Optional[Orchestrator] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global services, orchestrator
    hub.bind(asyncio.get_running_loop())
    services = Services(settings, hub)
    orchestrator = Orchestrator(services)
    pump = asyncio.create_task(hub.pump())
    await orchestrator.start()
    log.info("QUANT PILOT ready · %r", settings)
    yield
    await orchestrator.stop()
    pump.cancel()


app = FastAPI(title="QUANT PILOT", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def friendly_errors(_: Request, exc: Exception) -> JSONResponse:
    """Never leak stack traces to the UI."""
    log.exception("Unhandled API error")
    return JSONResponse(status_code=500, content={"ok": False, "message": "Something went wrong on the desk. It has been logged; please retry."})


def svc() -> Services:
    assert services is not None
    return services


def orch() -> Orchestrator:
    assert orchestrator is not None
    return orchestrator


# ============================================================ read endpoints
@app.get("/api/health")
async def health() -> dict:
    s = svc()
    return {"ok": True, "mode": s.mode_label(), "data_source": s.state.data_source, "execution": s.state.execution,
            "analyst": s.analyst.mode, "cycles": s.state.cycles, "ws_clients": len(hub.clients), "events_sent": hub.sent,
            "mt5_available": s.mt5.available, "mt5_connected": s.mt5.connected, "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/state")
async def state() -> dict:
    s = svc()
    return {
        "mode": s.mode_label(), "data_source": s.state.data_source, "execution": s.state.execution,
        "banner": s.state.banner, "analyst_mode": s.analyst.mode, "model": settings.anthropic_model,
        "instruments": list(INSTRUMENTS), "pipeline": PIPELINE_ORDER,
        "kpis": s.kpis(), "positions": s.positions(), "equity_curve": s.paper.equity_curve[-600:],
        "last_cycle": s.state.last_cycle,
        "session": session_info(datetime.fromtimestamp(s.clock(), tz=timezone.utc)),
        "rules": s.rules.to_dict(), "params": s.params.to_dict(),
        "mt5": s.mt5.last_health, "mt5_sync": s.state.mt5_sync, "confirm_phrase": CONFIRM_PHRASE,
        "kill_switch": s.guardian_state.kill_switch, "mt5_mode_env": settings.mt5_mode,
    }


@app.get("/api/candles")
async def candles(instrument: str = "XAUUSD", n: int = 400) -> dict:
    s = svc()
    if instrument not in INSTRUMENTS:
        return {"ok": False, "message": f"Unknown instrument {instrument}"}
    n = max(50, min(n, 2000))
    if s.state.data_source == "mt5" and s.mt5.connected:
        data = await asyncio.to_thread(s.mt5.rates, instrument, "M5", n)
    else:
        data = s.feed.candles(instrument, n)
    return {"ok": True, "instrument": instrument, "candles": data, "last_cycle": s.state.last_cycle.get(instrument)}


@app.get("/api/journal")
async def journal(limit: int = 150, outcome: Optional[str] = None) -> dict:
    s = svc()
    return {"decisions": s.db.decisions(limit, outcome), "trades": s.db.trades(200), "reviews": s.db.reviews()}


@app.get("/api/mt5/log")
async def mt5_log(limit: int = 100) -> dict:
    return {"log": svc().db.mt5_log(limit)}


# ============================================================ control endpoints
class ModeBody(BaseModel):
    data_source: Optional[str] = None
    execution: Optional[str] = None


@app.post("/api/mode")
async def set_mode(body: ModeBody) -> dict:
    s = svc()
    if body.execution == "mt5":
        h = await asyncio.to_thread(s.mt5.health)
        if not s.mt5.is_ready():
            fix = h["issues"][0]["fix"] if h.get("issues") else "Connect MetaTrader 5 first."
            return {"ok": False, "message": f"MT5 execution unavailable. {fix}"}
        s.state.execution, s.state.data_source = "mt5", "mt5"
    elif body.execution == "paper":
        s.state.execution = "paper"
    if body.data_source == "demo":
        if s.state.execution == "mt5":
            return {"ok": False, "message": "MT5 execution needs MT5 data. Switch execution to Paper first."}
        s.state.data_source = "demo"
    elif body.data_source == "mt5":
        if not s.mt5.connected:
            return {"ok": False, "message": "MT5 is not connected: staying on Demo data."}
        s.state.data_source = "mt5"
    s.state.banner = None
    s.state.last_seen_bar.clear()
    s.guardian_state.day_start_equity = s.equity()
    hub.emit("mode", {"mode": s.mode_label(), "data_source": s.state.data_source, "execution": s.state.execution})
    return {"ok": True, "mode": s.mode_label(), "data_source": s.state.data_source, "execution": s.state.execution}


class SettingsBody(BaseModel):
    rules: dict[str, Any] = {}
    params: dict[str, Any] = {}
    validate_only: bool = False


@app.put("/api/settings")
async def update_settings(body: SettingsBody) -> dict:
    s = svc()
    errors = s.rules.validate(body.rules) if body.rules else []
    if body.params:
        p = body.params
        lo, hi = float(p.get("xau_min_depth_pips", s.params.xau_min_depth_pips)), float(p.get("xau_max_depth_pips", s.params.xau_max_depth_pips))
        if lo >= hi:
            errors.append("XAU minimum sweep depth must be below the maximum.")
        blo, bhi = float(p.get("btc_min_depth_pct", s.params.btc_min_depth_pct)), float(p.get("btc_max_depth_pct", s.params.btc_max_depth_pct))
        if blo >= bhi:
            errors.append("BTC minimum sweep depth must be below the maximum.")
        if float(p.get("displacement_mult", s.params.displacement_mult)) < 1.0:
            errors.append("Displacement multiplier must be at least 1.0x.")
        if float(p.get("tp1_rr", s.params.tp1_rr)) < s.rules.min_rr:
            errors.append(f"TP1 RR cannot be below the Guardian's minimum (1:{s.rules.min_rr:g}).")
    if errors or body.validate_only:
        return {"ok": not errors, "errors": errors}
    if body.rules:
        s.rules.update(body.rules)
        s.db.kv_set("rules", s.rules.to_dict())
    if body.params:
        s.params.update(body.params)
        s.db.kv_set("params", s.params.to_dict())
    hub.emit("settings", {"rules": s.rules.to_dict(), "params": s.params.to_dict()})
    return {"ok": True, "errors": [], "rules": s.rules.to_dict(), "params": s.params.to_dict()}


class KillBody(BaseModel):
    engaged: bool
    close_all: bool = False


@app.post("/api/kill")
async def kill(body: KillBody) -> dict:
    return await asyncio.to_thread(orch().engage_kill_switch, body.engaged, body.close_all)


class ScenarioBody(BaseModel):
    instrument: Optional[str] = None


@app.post("/api/demo/scenario")
async def demo_scenario(body: ScenarioBody) -> dict:
    return orch().run_demo_scenario(body.instrument)


@app.post("/api/paper/close/{pos_id}")
async def paper_close(pos_id: str) -> dict:
    s = svc()
    pos = s.paper.positions.get(pos_id)
    if not pos:
        return {"ok": False, "message": "Position not found (it may have just closed)."}
    s.paper._close(pos, s.last_price(pos.instrument), "Manual close", s.clock())
    d = pos.model_dump()
    s.db.record_trade(d)
    hub.emit("position_event", {"instrument": pos.instrument, "type": "manual", "position": d})
    return {"ok": True, "position": d}


class BacktestBody(BaseModel):
    instrument: str = "XAUUSD"
    days: int = 45
    seed: int = 42


@app.post("/api/backtest")
async def backtest(body: BacktestBody) -> dict:
    s = svc()
    if body.instrument not in INSTRUMENTS:
        return {"ok": False, "message": "Unknown instrument"}
    days = max(10, min(body.days, 180))

    def prog(x: float) -> None:
        hub.emit("backtest_progress", {"progress": round(x, 3)})

    res = await asyncio.to_thread(run_backtest, body.instrument, days, s.rules, s.params, settings.starting_balance, None, body.seed, prog)
    return {"ok": True, **res}


@app.post("/api/review")
async def review_now() -> dict:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = await asyncio.to_thread(orch().write_review, day)
    return {"ok": True, "day": day, "text": text}


# ============================================================ MT5 endpoints
@app.get("/api/mt5/status")
async def mt5_status() -> dict:
    s = svc()
    return {**(await asyncio.to_thread(s.mt5.health)), "mode": s.mode_label()}


@app.get("/api/mt5/symbols")
async def mt5_symbols() -> dict:
    s = svc()
    return {"candidates": await asyncio.to_thread(s.mt5.detect_symbols), "mapping": s.mt5.symbol_map}


class SymbolMapBody(BaseModel):
    mapping: dict[str, str]


@app.put("/api/mt5/symbols")
async def mt5_set_symbols(body: SymbolMapBody) -> dict:
    s = svc()
    s.mt5.set_symbol_map(body.mapping)
    h = await asyncio.to_thread(s.mt5.health)
    return {"ok": True, "mapping": s.mt5.symbol_map, "symbols": h.get("symbols", {})}


class LiveBody(BaseModel):
    enable: bool
    phrase: str = ""


@app.post("/api/mt5/live")
async def mt5_live(body: LiveBody) -> dict:
    s = svc()
    if not body.enable:
        s.mt5.live_unlocked = False
        return {"ok": True, "live_unlocked": False, "message": "Live trading locked. DEMO ACCOUNT ONLY."}
    if settings.mt5_mode != "live":
        return {"ok": False, "live_unlocked": False,
                "message": "Live is hard-disabled: set MT5_MODE=live in .env and restart to allow unlocking."}
    if body.phrase.strip() != CONFIRM_PHRASE:
        return {"ok": False, "live_unlocked": False, "message": f'Type exactly "{CONFIRM_PHRASE}" to unlock live trading.'}
    s.mt5.live_unlocked = True
    s.toast("error", "LIVE TRADING UNLOCKED", "Orders may now be sent to a real-money account. Risk of loss is real.")
    return {"ok": True, "live_unlocked": True, "message": "Live trading unlocked for this session."}


class TestOrderBody(BaseModel):
    instrument: str = "XAUUSD"


@app.post("/api/mt5/test-order")
async def mt5_test_order(body: TestOrderBody) -> dict:
    s = svc()
    if not s.mt5.is_ready():
        h = s.mt5.last_health
        return {"ok": False, "message": h["issues"][0]["fix"] if h.get("issues") else "MT5 is not connected."}
    res = await asyncio.to_thread(s.mt5.send_test_order, body.instrument, 3.0)
    s.toast("success" if res.get("ok") else "error", "MT5 test order", res.get("message", ""))
    return res


@app.post("/api/mt5/close/{ticket}")
async def mt5_close(ticket: int) -> dict:
    res = await asyncio.to_thread(svc().mt5.close_position, ticket, None, "Manual close")
    return res.to_dict()


@app.post("/api/mt5/reconnect")
async def mt5_reconnect() -> dict:
    s = svc()
    await asyncio.to_thread(s.mt5.connect)
    return await asyncio.to_thread(s.mt5.health)


# ============================================================ websocket
@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    hub.clients.add(websocket)
    s = svc()
    await websocket.send_json({"type": "hello", "data": {"mode": s.mode_label(), "pipeline": PIPELINE_ORDER}})
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(websocket)
