"""AEGIS risk rules: hard-coded vetoes and position sizing.

Nothing reaches execution unless every check here passes. The Analyst (LLM) can
only lower confidence or reject; it can never bypass these rules.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from .indicators import SPECS, InstrumentSpec


@dataclass
class RiskRules:
    """Editable guardrails. Validation bounds are enforced in ``validate``."""

    risk_per_trade_pct: float = 1.0
    max_risk_per_trade_pct: float = 2.0
    daily_drawdown_kill_pct: float = 4.0
    max_open_trades: int = 2
    min_rr: float = 2.0
    min_confidence: int = 7
    spread_limit_xau_points: float = 35.0
    spread_limit_btc_points: float = 3000.0
    session_filter: bool = True
    allowed_sessions_xau: list[str] = field(default_factory=lambda: ["LONDON", "NEW_YORK"])
    cooldown_minutes: int = 30
    news_filter: bool = True
    news_hours_utc: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self, values: dict) -> list[str]:
        """Return a list of human-readable validation errors for proposed new values."""
        errs: list[str] = []
        merged = {**self.to_dict(), **values}
        if not 0.1 <= float(merged["risk_per_trade_pct"]) <= 2.0:
            errs.append("Risk per trade must be between 0.1% and 2%.")
        if float(merged["risk_per_trade_pct"]) > float(merged["max_risk_per_trade_pct"]):
            errs.append("Risk per trade cannot exceed the max risk per trade.")
        if not 0.5 <= float(merged["max_risk_per_trade_pct"]) <= 2.0:
            errs.append("Max risk per trade is capped at 2%.")
        if not 1.0 <= float(merged["daily_drawdown_kill_pct"]) <= 10.0:
            errs.append("Daily drawdown kill must be between 1% and 10%.")
        if not 1 <= int(merged["max_open_trades"]) <= 10:
            errs.append("Max open trades must be between 1 and 10.")
        if float(merged["min_rr"]) < 1.0:
            errs.append("Minimum RR cannot be below 1:1.")
        if not 1 <= int(merged["min_confidence"]) <= 10:
            errs.append("Minimum confidence must be between 1 and 10.")
        if float(merged["spread_limit_xau_points"]) <= 0 or float(merged["spread_limit_btc_points"]) <= 0:
            errs.append("Spread limits must be positive.")
        if int(merged["cooldown_minutes"]) < 0:
            errs.append("Cooldown cannot be negative.")
        return errs

    def update(self, values: dict) -> list[str]:
        errs = self.validate(values)
        if errs:
            return errs
        for k, v in values.items():
            if hasattr(self, k):
                cur = getattr(self, k)
                setattr(self, k, v if isinstance(cur, list) else type(cur)(v))
        return []


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def normalize_volume(raw: float, vmin: float, vstep: float, vmax: float) -> float:
    """Floor a volume to the broker's step and clamp to [min, max]. Returns 0 if below min."""
    if raw < vmin:
        return 0.0
    steps = math.floor((raw - vmin) / vstep + 1e-9)
    vol = vmin + steps * vstep
    vol = min(vol, vmax)
    decimals = max(0, -int(math.floor(math.log10(vstep)))) if vstep < 1 else 0
    return round(vol, decimals)


def lot_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    spec: InstrumentSpec,
    tick_value: Optional[float] = None,
    tick_size: Optional[float] = None,
) -> tuple[float, float]:
    """Volume that risks ``risk_pct`` of equity between entry and stop.

    Returns (normalized_volume, actual_risk_amount). Uses broker tick value when
    provided (MT5), otherwise the static contract size.
    """
    dist = abs(entry - stop)
    if dist <= 0 or equity <= 0:
        return 0.0, 0.0
    risk_amount = equity * risk_pct / 100.0
    if tick_value and tick_size:
        loss_per_lot = dist / tick_size * tick_value
    else:
        loss_per_lot = dist * spec.contract_size
    raw = risk_amount / loss_per_lot
    vol = normalize_volume(raw, spec.volume_min, spec.volume_step, spec.volume_max)
    return vol, round(vol * loss_per_lot, 2)


@dataclass
class GuardianState:
    """Mutable state the Guardian needs across cycles."""

    kill_switch: bool = False
    day_start_equity: float = 0.0
    day_key: str = ""
    recent_signals: dict[str, float] = field(default_factory=dict)  # signal_id / level key -> ts
    processed_ids: set[str] = field(default_factory=set)


def evaluate(
    rules: RiskRules,
    state: GuardianState,
    *,
    instrument: str,
    direction: str,
    entry: float,
    stop: float,
    tp1: float,
    confidence: int,
    session: str,
    spread_points: float,
    equity: float,
    open_trades: int,
    signal_id: str,
    level_key: str,
    candle_hour_utc: int,
    analyst_bias: str,
    spec: Optional[InstrumentSpec] = None,
    tick_value: Optional[float] = None,
    tick_size: Optional[float] = None,
    now: Optional[float] = None,
) -> tuple[list[Check], float, float]:
    """Run every AEGIS check. Returns (checks, volume, risk_amount). Approved iff all checks pass."""
    now = now or time.time()
    spec = spec or SPECS[instrument]
    checks: list[Check] = []

    checks.append(Check("Kill switch", not state.kill_switch, "Kill switch engaged: no new orders." if state.kill_switch else "Off"))

    bias_ok = analyst_bias != "NO_TRADE"
    checks.append(Check("Analyst bias", bias_ok, "Analyst returned NO_TRADE." if not bias_ok else analyst_bias))

    limit = rules.spread_limit_xau_points if instrument == "XAUUSD" else rules.spread_limit_btc_points
    checks.append(Check("Spread", spread_points <= limit, f"{spread_points:.0f} pts (limit {limit:.0f})"))

    dd = 0.0
    if state.day_start_equity > 0:
        dd = max(0.0, (state.day_start_equity - equity) / state.day_start_equity * 100)
    checks.append(Check("Daily drawdown", dd < rules.daily_drawdown_kill_pct, f"{dd:.2f}% today (kill at {rules.daily_drawdown_kill_pct}%)"))

    checks.append(Check("Max open trades", open_trades < rules.max_open_trades, f"{open_trades} open (max {rules.max_open_trades})"))

    risk = abs(entry - stop)
    rr = abs(tp1 - entry) / risk if risk > 0 else 0.0
    geom_ok = (direction == "LONG" and stop < entry < tp1) or (direction == "SHORT" and stop > entry > tp1)
    checks.append(Check("Risk:Reward", geom_ok and rr + 1e-9 >= rules.min_rr, f"1:{rr:.2f} (min 1:{rules.min_rr:g})" if geom_ok else "Invalid SL/TP geometry"))

    checks.append(Check("Confidence", confidence >= rules.min_confidence, f"{confidence}/10 (min {rules.min_confidence})"))

    if rules.session_filter and spec.sessions_matter:
        ok = session in rules.allowed_sessions_xau
        checks.append(Check("Session", ok, f"{session} ({'allowed' if ok else 'gold trades London/NY only'})"))
    else:
        checks.append(Check("Session", True, f"{session} (context only)"))

    news_hit = rules.news_filter and candle_hour_utc in rules.news_hours_utc
    checks.append(Check("News filter", not news_hit, "High-impact news hour" if news_hit else "Clear"))

    dup = signal_id in state.processed_ids
    last = state.recent_signals.get(level_key)
    cooling = last is not None and (now - last) < rules.cooldown_minutes * 60
    checks.append(Check("Duplicate / cooldown", not dup and not cooling, "Duplicate signal" if dup else ("Level on cooldown" if cooling else "Fresh signal")))

    risk_pct = min(rules.risk_per_trade_pct, rules.max_risk_per_trade_pct)
    vol, risk_amt = lot_size(equity, risk_pct, entry, stop, spec, tick_value, tick_size)
    checks.append(Check("Position size", vol > 0, f"{vol} lots risking ${risk_amt:,.2f} ({risk_pct}%)" if vol > 0 else "Stop too wide for minimum lot at this risk"))
    if vol > 0 and equity > 0 and risk_amt / equity * 100 > rules.max_risk_per_trade_pct + 1e-6:
        checks[-1] = Check("Position size", False, f"Minimum lot risks {risk_amt / equity * 100:.2f}% (> {rules.max_risk_per_trade_pct}%)")

    return checks, vol, risk_amt
