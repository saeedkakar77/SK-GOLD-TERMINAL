"""Orchestrator: owns all services and runs the 7-agent pipeline every 5M candle close."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..agents import (AnalystAgent, CartographerAgent, ChroniclerAgent, ExecutionerAgent, GuardianAgent, HunterAgent,
                      PIPELINE_ORDER, ScoutAgent)
from ..agents.base import CycleContext
from ..agents.chronicler import build_daily_review
from ..config import INSTRUMENTS, Settings
from .db import Database
from .demo_data import DemoFeed
from .events import EventHub
from .indicators import session_for, session_info
from .models import AgentStatus
from .mt5_client import MT5Bridge
from .paper_engine import PaperEngine
from .risk import GuardianState, RiskRules
from .strategy import StrategyParams, map_liquidity

log = logging.getLogger("quantpilot.orchestrator")


@dataclass
class RuntimeState:
    data_source: str = "demo"  # demo | mt5
    execution: str = "paper"  # paper | mt5
    paused: bool = False
    scenario_until: float = 0.0
    banner: Optional[str] = None
    cycles: int = 0
    last_cycle: dict[str, dict] = field(default_factory=dict)
    mt5_sync: dict = field(default_factory=lambda: {"positions": [], "deals": []})
    last_seen_bar: dict[str, int] = field(default_factory=dict)


class Services:
    """Dependency container passed to agents through the cycle context."""

    def __init__(self, settings: Settings, hub: EventHub, mt5_module: Any = None) -> None:
        self.settings = settings
        self.hub = hub
        self.db = Database(settings.db_path)
        self.rules = RiskRules(**(self.db.kv_get("rules", {}) or {}))
        self.params = StrategyParams(**(self.db.kv_get("params", {}) or {}))
        self.guardian_state = GuardianState()
        self.state = RuntimeState()
        self.feed = DemoFeed(INSTRUMENTS)
        self.paper = PaperEngine(settings.starting_balance)
        self.mt5 = MT5Bridge(self.db, login=settings.mt5_login, password=settings.mt5_password, server=settings.mt5_server,
                             path=settings.mt5_path, magic=settings.mt5_magic, deviation=settings.mt5_deviation,
                             mt5_module=mt5_module, allow_live_env=settings.mt5_mode == "live",
                             on_event=lambda kind, payload: self.hub.emit(kind, payload))
        self.analyst = AnalystAgent(settings.anthropic_api_key, settings.anthropic_model, settings.analyst_timeout_s)
        self.agents = [ScoutAgent(), CartographerAgent(), HunterAgent(), self.analyst, GuardianAgent(),
                       ExecutionerAgent(), ChroniclerAgent()]
        self.trades_taken = 0
        self.last_prices: dict[str, float] = {}

    # ---------------------------------------------------------------- helpers used by agents
    def clock(self) -> float:
        if self.state.data_source == "demo":
            return float(self.feed.markets[INSTRUMENTS[0]].candles[-1]["time"])
        return time.time()

    def equity(self) -> float:
        if self.state.execution == "mt5":
            acc = self.mt5.last_health.get("account") or {}
            if acc.get("equity") is not None:
                return float(acc["equity"])
        return self.paper.equity()

    def balance(self) -> float:
        if self.state.execution == "mt5":
            acc = self.mt5.last_health.get("account") or {}
            if acc.get("balance") is not None:
                return float(acc["balance"])
        return round(self.paper.balance, 2)

    def open_trade_count(self) -> int:
        if self.state.execution == "mt5":
            return len([p for p in self.state.mt5_sync.get("positions", []) if p.get("quantpilot")])
        return len(self.paper.positions)

    def last_price(self, instrument: str) -> float:
        if self.state.data_source == "demo":
            return self.feed.last_price(instrument)
        return self.last_prices.get(instrument) or self.feed.last_price(instrument)

    def toast(self, level: str, title: str, message: str) -> None:
        self.hub.emit("toast", {"level": level, "title": title, "message": message})

    def on_trade_placed(self, ctx: CycleContext, *, venue: str, ticket: Optional[int], price: Optional[float], volume: Optional[float]) -> None:
        self.trades_taken += 1
        setup = ctx.setup
        assert setup is not None
        title = f"Trade placed on MT5 · Ticket #{ticket}" if venue == "mt5" else "Paper trade opened"
        self.hub.emit("trade_placed", {"venue": venue, "ticket": ticket, "price": price, "volume": volume,
                                       "instrument": ctx.instrument, "direction": setup.direction, "signal_id": setup.signal_id,
                                       "first": self.trades_taken == 1})
        self.toast("success", title, f"{setup.direction} {volume} {ctx.instrument} @ {price}")

    def mode_label(self) -> str:
        if self.state.execution == "mt5":
            return "MT5 DEMO" if self.mt5.account_mode() == "DEMO" else "MT5 LIVE"
        return "PAPER" if self.state.data_source == "mt5" else "DEMO"

    def kpis(self) -> dict:
        eq = self.equity()
        start = self.guardian_state.day_start_equity or eq
        trades = self.db.trades(500)
        wins = [t for t in trades if (t["pnl"] or 0) > 0]
        dd = max(0.0, (start - eq) / start * 100) if start else 0.0
        open_risk = self.paper.open_risk() if self.state.execution == "paper" else 0.0
        return {"equity": round(eq, 2), "balance": self.balance(), "today_pnl": round(eq - start, 2),
                "today_pnl_pct": round((eq - start) / start * 100, 3) if start else 0.0,
                "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0, "trades": len(trades),
                "open_risk": open_risk, "open_risk_pct": round(open_risk / eq * 100, 2) if eq else 0.0,
                "drawdown_pct": round(dd, 3), "dd_limit_pct": self.rules.daily_drawdown_kill_pct,
                "kill_switch": self.guardian_state.kill_switch}

    def positions(self) -> list[dict]:
        if self.state.execution == "mt5":
            return self.state.mt5_sync.get("positions", [])
        return [p.model_dump() for p in self.paper.open_positions()]


class Orchestrator:
    """Runs the agent pipeline, the demo replay, and the MT5 health/sync loops."""

    def __init__(self, services: Services) -> None:
        self.svc = services
        self._tasks: list[asyncio.Task] = []
        self._mt5_was_ok: Optional[bool] = None

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        svc = self.svc
        if svc.mt5.available:
            ok = await asyncio.to_thread(svc.mt5.connect)
            health = await asyncio.to_thread(svc.mt5.health)
            if ok and not svc.settings.demo_mode and health.get("connected"):
                svc.state.data_source = "mt5"
            elif not svc.settings.demo_mode:
                svc.state.banner = "MT5 unavailable: running in Demo mode. " + (health["issues"][0]["fix"] if health["issues"] else "")
        else:
            if not svc.settings.demo_mode:
                svc.state.banner = svc.mt5.unavailable_reason()
            svc.mt5.health()
        self._reset_day(force=True)
        self._tasks = [asyncio.create_task(self._cycle_loop(), name="cycle"),
                       asyncio.create_task(self._mt5_health_loop(), name="mt5-health"),
                       asyncio.create_task(self._mt5_sync_loop(), name="mt5-sync")]
        log.info("Orchestrator started (data=%s exec=%s analyst=%s)", svc.state.data_source, svc.state.execution, svc.analyst.mode)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.to_thread(self.svc.mt5.shutdown)

    # ---------------------------------------------------------------- day handling
    def _reset_day(self, force: bool = False) -> None:
        svc = self.svc
        key = datetime.fromtimestamp(svc.clock(), tz=timezone.utc).strftime("%Y-%m-%d")
        gs = svc.guardian_state
        if force or key != gs.day_key:
            prev = gs.day_key
            gs.day_key = key
            gs.day_start_equity = svc.equity()
            if prev and not force:
                asyncio.get_running_loop().run_in_executor(None, self.write_review, prev)

    def write_review(self, day: str) -> str:
        svc = self.svc
        since = time.time() - 86400
        text = build_daily_review(svc.db.decisions_since(since), svc.db.trades_since(since), svc.analyst.client, svc.settings.anthropic_model)
        svc.db.save_review(day, text)
        svc.hub.emit("review", {"day": day, "text": text})
        return text

    # ---------------------------------------------------------------- pipeline
    def run_pipeline(self, instrument: str, pace: float = 0.0) -> CycleContext:
        """Run all seven agents in order for one instrument (blocking; call from a worker thread)."""
        svc = self.svc
        ctx = CycleContext(instrument=instrument, cycle_id=uuid.uuid4().hex[:8], services=svc)
        svc.hub.emit("cycle_start", {"instrument": instrument, "cycle_id": ctx.cycle_id})
        for agent in svc.agents:
            if ctx.halted and agent.name != "Chronicler":
                continue
            if agent.name == "Chronicler" and ctx.setup is None:
                break
            res = agent.run(ctx)
            svc.hub.emit("agent", {"instrument": instrument, "cycle_id": ctx.cycle_id, **res.model_dump()})
            if pace and ctx.setup is not None and agent.name != "Chronicler":
                time.sleep(pace)
        summary = {
            "instrument": instrument, "cycle_id": ctx.cycle_id, "outcome": ctx.outcome, "ts": time.time(),
            "setup": ctx.setup.model_dump() if ctx.setup else None,
            "decision": ctx.decision.model_dump() if ctx.decision else None,
            "checks": ctx.checks, "levels": [lv.model_dump() for lv in ctx.levels],
            "trace": [r.model_dump() for r in ctx.trace], "execution": ctx.execution,
        }
        if ctx.setup is not None or instrument not in svc.state.last_cycle:
            svc.state.last_cycle[instrument] = summary
        else:  # keep the last interesting setup but refresh levels
            svc.state.last_cycle[instrument]["levels"] = summary["levels"]
        svc.hub.emit("cycle_end", summary)
        if ctx.outcome == "vetoed":
            veto = next((r for r in ctx.trace if r.status == AgentStatus.VETO), None)
            svc.toast("warning", f"AEGIS veto · {instrument}", veto.summary[:180] if veto else "Vetoed")
        return ctx

    def _handle_paper_events(self, instrument: str, events: list[dict]) -> None:
        svc = self.svc
        for ev in events:
            pos = ev["position"]
            if ev["type"] in ("sl", "stop", "tp2"):
                pos["venue"] = "paper"
                svc.db.record_trade(pos)
            svc.hub.emit("position_event", {"instrument": instrument, **ev})
            title = {"tp1": "TP1 hit · 50% closed", "tp2": "TP2 hit · trade closed", "be": "Stop moved to break-even",
                     "sl": "Stop loss hit", "stop": ev.get("reason", "Stopped")}[ev["type"]]
            level = "success" if ev["type"] in ("tp1", "tp2") else ("info" if ev["type"] in ("be", "stop") else "error")
            svc.toast(level, title, f"{pos['instrument']} {pos['direction']} · realized ${pos['realized_pnl']:,.2f}")

    def broadcast_market(self, candles: dict[str, dict]) -> None:
        svc = self.svc
        for inst, c in candles.items():
            svc.last_prices[inst] = float(c["close"])
        svc.hub.emit("market", {
            "candles": candles, "kpis": svc.kpis(), "positions": svc.positions(),
            "equity_point": {"time": int(svc.clock()), "equity": svc.equity()},
            "session": session_info(datetime.fromtimestamp(svc.clock(), tz=timezone.utc)),
            "mode": svc.mode_label(),
        })

    async def _cycle_loop(self) -> None:
        svc = self.svc
        while True:
            try:
                if svc.state.paused:
                    await asyncio.sleep(0.5)
                    continue
                scenario = time.time() < svc.state.scenario_until
                if svc.state.data_source == "demo":
                    new = svc.feed.advance()
                    self._reset_day()
                    for inst, candle in new.items():
                        self._handle_paper_events(inst, svc.paper.on_candle(inst, candle))
                    self.broadcast_market(new)
                    for inst in INSTRUMENTS:
                        await asyncio.to_thread(self.run_pipeline, inst, 0.35)
                    svc.state.cycles += 1
                    await asyncio.sleep(0.9 if scenario else svc.settings.demo_cycle_seconds)
                else:
                    await self._mt5_cycle()
                    await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the desk alive
                log.exception("cycle loop error")
                svc.toast("error", "Cycle error", "An internal error occurred; the desk will retry automatically.")
                await asyncio.sleep(3)

    async def _mt5_cycle(self) -> None:
        svc = self.svc
        if not svc.mt5.connected:
            svc.state.data_source = "demo"
            svc.state.execution = "paper"
            svc.state.banner = "MT5 disconnected: switched to Demo mode automatically."
            svc.toast("error", "MT5 disconnected", "Switched to Demo/Paper mode. Re-open MetaTrader 5 to reconnect.")
            return
        new: dict[str, dict] = {}
        for inst in INSTRUMENTS:
            bars = await asyncio.to_thread(svc.mt5.rates, inst, "M5", 3)
            if not bars:
                continue
            last = bars[-1]
            if last["time"] > svc.state.last_seen_bar.get(inst, 0):
                svc.state.last_seen_bar[inst] = last["time"]
                new[inst] = last
        self._reset_day()
        for inst, candle in new.items():
            if svc.state.execution == "paper":
                self._handle_paper_events(inst, svc.paper.on_candle(inst, candle))
        if new:
            self.broadcast_market(new)
            for inst in new:
                await asyncio.to_thread(self.run_pipeline, inst, 0.0)
            svc.state.cycles += 1

    async def _mt5_health_loop(self) -> None:
        svc = self.svc
        while True:
            try:
                h = await asyncio.to_thread(svc.mt5.health)
                ok = bool(h.get("connected")) and not h["issues"]
                if self._mt5_was_ok is not None and ok != self._mt5_was_ok and svc.mt5.available:
                    if ok:
                        svc.toast("success", "MT5 ready", f"Connected to {(h.get('account') or {}).get('server', 'terminal')}.")
                    elif h["issues"]:
                        svc.toast("error", "MT5 check failed", h["issues"][0]["fix"])
                self._mt5_was_ok = ok
                svc.hub.emit("mt5_status", {**h, "mode": svc.mode_label()})
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("mt5 health loop error")
            await asyncio.sleep(10)

    async def _mt5_sync_loop(self) -> None:
        svc = self.svc
        while True:
            try:
                if svc.mt5.connected:
                    if svc.state.execution == "mt5":
                        events = await asyncio.to_thread(svc.mt5.manage_positions)
                        for ev in events:
                            svc.toast("success" if ev["type"] == "tp1" else "info",
                                      "TP1 · 50% closed on MT5" if ev["type"] == "tp1" else "MT5 stop moved to break-even",
                                      f"Ticket #{ev['ticket']}")
                    snap = await asyncio.to_thread(svc.mt5.sync)
                    svc.state.mt5_sync = snap
                    svc.hub.emit("mt5_sync", snap)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("mt5 sync loop error")
            await asyncio.sleep(2)

    # ---------------------------------------------------------------- actions
    def run_demo_scenario(self, instrument: Optional[str] = None) -> dict:
        """Plant a textbook sweep in the demo feed and speed up the replay so it plays out in ~30s."""
        svc = self.svc
        if svc.state.data_source != "demo":
            return {"ok": False, "message": "Demo scenarios run in Demo mode only."}
        if instrument is None:
            sess = session_for(svc.clock())
            instrument = "XAUUSD" if sess in svc.rules.allowed_sessions_xau else "BTCUSD"
        market = svc.feed.markets[instrument]
        if market.plan is not None:
            return {"ok": False, "message": "A sweep is already playing out. Watch the chart!"}
        from .indicators import to_frame

        df = to_frame(market.candles[-900:])
        levels = map_liquidity(df, instrument, svc.params)
        plan = market.force_scenario([(lv.side, lv.price) for lv in levels])
        if not plan:
            return {"ok": False, "message": "No suitable liquidity level near price right now; try again shortly."}
        # make sure the planted level is not on cooldown from earlier demo signals
        svc.guardian_state.recent_signals = {k: v for k, v in svc.guardian_state.recent_signals.items() if not k.startswith(instrument)}
        svc.state.scenario_until = time.time() + 40
        svc.toast("info", "Demo scenario armed", f"{instrument}: price will hunt the {plan['side']} at {plan['level']:.2f}.")
        return {"ok": True, "instrument": instrument, **plan}

    def engage_kill_switch(self, engaged: bool, close_all: bool) -> dict:
        svc = self.svc
        svc.guardian_state.kill_switch = engaged
        closed: list[Any] = []
        if engaged and close_all:
            prices = {s: svc.last_price(s) for s in INSTRUMENTS}
            for p in svc.paper.close_all(prices):
                d = p.model_dump()
                svc.db.record_trade(d)
                closed.append(d["id"])
            if svc.mt5.connected:
                closed += [r.ticket for r in svc.mt5.close_all_magic()]
        svc.hub.emit("kill_switch", {"engaged": engaged, "closed": closed})
        svc.toast("error" if engaged else "success", "KILL SWITCH ENGAGED" if engaged else "Kill switch released",
                  f"New orders blocked.{f' Closed {len(closed)} position(s).' if closed else ''}" if engaged else "AEGIS will accept new signals again.")
        return {"ok": True, "engaged": engaged, "closed": closed}


__all__ = ["Services", "Orchestrator", "RuntimeState", "PIPELINE_ORDER"]
