"""Backtest Lab: replays history through the same Hunter + Analyst(mock) + Guardian + paper engine rules."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional

from ..agents.analyst import mock_decision
from .demo_data import DemoMarket
from .indicators import to_frame
from .paper_engine import PaperEngine
from .risk import GuardianState, RiskRules, evaluate
from .strategy import StrategyParams, detect_at, map_liquidity

log = logging.getLogger("quantpilot.backtest")


def run_backtest(
    instrument: str,
    days: int,
    rules: RiskRules,
    params: StrategyParams,
    starting_balance: float = 10000.0,
    candles: Optional[list[dict]] = None,
    seed: int = 42,
    progress: Optional[Callable[[float], None]] = None,
) -> dict:
    """Run a full backtest and return stats, equity curve, trade markers and monthly returns."""
    t0 = time.time()
    if candles is None:
        market = DemoMarket(instrument, seed=seed, history_days=days, max_candles=days * 288 + 2000)
        candles = market.candles
    df = to_frame(candles)
    n = len(df)
    engine = PaperEngine(starting_balance)
    engine.equity_curve = []
    gs = GuardianState(day_start_equity=starting_balance)
    typical_spread = 25.0 if instrument == "XAUUSD" else 1800.0
    levels: list = []
    markers: list[dict] = []
    decisions = {"taken": 0, "vetoed": 0, "skipped": 0}
    veto_reasons: dict[str, int] = defaultdict(int)
    curve: list[dict] = []
    rows = df.to_dict("records")
    start_i = 300
    for i in range(start_i, n):
        c = rows[i]
        ts = int(c["time"])
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if day != gs.day_key:
            gs.day_key, gs.day_start_equity = day, engine.equity()
        for ev in engine.on_candle(instrument, c):
            if ev["type"] in ("sl", "stop", "tp2"):
                p = ev["position"]
                markers.append({"time": int(p["closed_at"]), "type": "exit", "pnl": p["realized_pnl"], "reason": p["close_reason"]})
        if i % 24 == 0 or not levels:
            levels = map_liquidity(df.iloc[max(0, i - 600) : i - params.confirm_candles], instrument, params)
        for setup in detect_at(df, i, levels, instrument, params):
            dec = mock_decision(setup)
            checks, vol, _ = evaluate(
                rules, gs, instrument=instrument, direction=setup.direction, entry=setup.entry_price, stop=setup.stop_loss,
                tp1=setup.take_profit_1, confidence=dec.confidence_score, session=setup.session, spread_points=typical_spread,
                equity=engine.equity(), open_trades=len(engine.positions), signal_id=setup.signal_id,
                level_key=f"{instrument}:{setup.level.name}", candle_hour_utc=datetime.fromtimestamp(ts, tz=timezone.utc).hour,
                analyst_bias=dec.bias, now=float(ts),
            )
            gs.processed_ids.add(setup.signal_id)
            failed = [ch for ch in checks if not ch.passed]
            if failed:
                decisions["vetoed"] += 1
                for ch in failed:
                    veto_reasons[ch.name] += 1
                continue
            gs.recent_signals[f"{instrument}:{setup.level.name}"] = float(ts)
            engine.open(signal_id=setup.signal_id, instrument=instrument, direction=setup.direction, volume=vol,
                        price=setup.entry_price, sl=setup.stop_loss, tp1=setup.take_profit_1, tp2=setup.take_profit_2, ts=ts)
            decisions["taken"] += 1
            markers.append({"time": ts, "type": "entry", "direction": setup.direction, "price": setup.entry_price, "level": setup.level.name})
        if i % 12 == 0:
            curve.append({"time": ts, "equity": engine.equity()})
        if progress and i % 500 == 0:
            progress((i - start_i) / max(1, n - start_i))
    engine.close_all({instrument: rows[-1]["close"]}, "End of test")
    curve.append({"time": int(rows[-1]["time"]), "equity": engine.equity()})

    trades = engine.closed
    pnls = [t.realized_pnl for t in trades]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    peak, max_dd = starting_balance, 0.0
    for pt in curve:
        peak = max(peak, pt["equity"])
        max_dd = max(max_dd, (peak - pt["equity"]) / peak * 100 if peak else 0)

    monthly: dict[str, float] = defaultdict(float)
    for t in trades:
        key = datetime.fromtimestamp(t.closed_at or t.opened_at, tz=timezone.utc).strftime("%Y-%m")
        monthly[key] += t.realized_pnl
    month_rows, eq = [], starting_balance
    for k in sorted(monthly):
        month_rows.append({"month": k, "pnl": round(monthly[k], 2), "pct": round(monthly[k] / eq * 100, 2)})
        eq += monthly[k]

    final = engine.equity()
    return {
        "instrument": instrument, "days": days, "candles": n, "elapsed_s": round(time.time() - t0, 2),
        "stats": {
            "trades": len(trades), "win_rate": round(len([p for p in pnls if p > 0]) / len(pnls) * 100, 1) if pnls else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0.0),
            "max_drawdown_pct": round(max_dd, 2), "net_pnl": round(final - starting_balance, 2),
            "return_pct": round((final - starting_balance) / starting_balance * 100, 2),
            "avg_win": round(gross_win / max(1, len([p for p in pnls if p > 0])), 2),
            "avg_loss": round(-gross_loss / max(1, len([p for p in pnls if p < 0])), 2),
            "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            "final_equity": round(final, 2), "starting_balance": starting_balance,
        },
        "decisions": decisions, "veto_reasons": dict(veto_reasons),
        "equity_curve": curve, "markers": markers, "monthly": month_rows,
        "trades": [{"time": int(t.opened_at), "closed": int(t.closed_at or 0), "direction": t.direction,
                    "entry": t.entry_price, "exit": t.exit_price, "pnl": t.realized_pnl, "reason": t.close_reason} for t in trades],
        "disclaimer": "Backtests on synthetic or historical data do not guarantee future results.",
    }
