"""Synthetic XAUUSD / BTCUSD 5M market with session-aware volatility and planted liquidity sweeps.

The generator is stateful: it pre-rolls history, then emits one new candle per
orchestrator cycle. Each trading day it plans one stop-hunt against the Asian
range; ``force_scenario`` plants a textbook sweep immediately (for demos).
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from .indicators import SPECS, session_for

log = logging.getLogger("quantpilot.demo")

FIVE_MIN = 300
BASE: dict[str, dict[str, float]] = {
    "XAUUSD": {"price": 2650.0, "vol": 0.55, "depth_lo": 12, "depth_hi": 22, "vol_base": 900},
    "BTCUSD": {"price": 95000.0, "vol": 0.0011, "depth_lo": 0.18, "depth_hi": 0.34, "vol_base": 140},
}
SESSION_VOL = {"ASIAN": 0.6, "LONDON": 1.25, "NEW_YORK": 1.35, "OFF_HOURS": 0.5}


@dataclass
class SweepPlan:
    """A scripted stop-hunt in progress."""

    side: Literal["high", "low"]
    level: float
    success: bool
    phase: str = "approach"  # approach -> sweep -> displace -> follow -> done
    step: int = 0
    approach_len: int = 8
    follow_len: int = 22
    depth_frac: float = 0.5
    start_price: float = 0.0


@dataclass
class DemoMarket:
    """Stateful synthetic market for one instrument."""

    instrument: str
    seed: int = 7
    history_days: int = 9
    candles: list[dict] = field(default_factory=list)
    rng: random.Random = field(init=False)
    plan: Optional[SweepPlan] = field(default=None, init=False)
    day_trigger: dict[str, int] = field(default_factory=dict, init=False)
    scenario_active: bool = field(default=False, init=False)
    max_candles: int = 6000
    end_ts: Optional[int] = None

    def __post_init__(self) -> None:
        self._asia: dict[int, tuple[float, float, int]] = {}
        self.rng = random.Random(self.seed + (0 if self.instrument == "XAUUSD" else 1000))
        self.cfg = BASE[self.instrument]
        self.spec = SPECS[self.instrument]
        now = (self.end_ts or int(time.time())) // FIVE_MIN * FIVE_MIN
        start = now - self.history_days * 86400
        # align start to midnight UTC so day structure is clean
        start = start - start % 86400
        self._t = start
        self._price = self.cfg["price"]
        n = (now - start) // FIVE_MIN
        for _ in range(n):
            self.step()
        log.info("Demo market %s pre-rolled %d candles", self.instrument, len(self.candles))

    # ------------------------------------------------------------ helpers
    def _abs_vol(self, price: float) -> float:
        v = self.cfg["vol"]
        return v if self.instrument == "XAUUSD" else price * v

    def _round(self, x: float) -> float:
        return round(x, self.spec.digits)

    def _avg_body(self, n: int = 20) -> float:
        tail = self.candles[-n:]
        if not tail:
            return self._abs_vol(self._price)
        return sum(abs(c["close"] - c["open"]) for c in tail) / len(tail) or self._abs_vol(self._price)

    def _depth(self, level: float, frac: float) -> float:
        lo, hi = self.cfg["depth_lo"], self.cfg["depth_hi"]
        d = lo + (hi - lo) * frac
        return d * self.spec.pip_size if self.instrument == "XAUUSD" else level * d / 100.0

    def _margin(self, level: float) -> float:
        return 3 * self.spec.pip_size if self.instrument == "XAUUSD" else level * 0.0006

    def _asia_range(self, day_start: int) -> Optional[tuple[float, float]]:
        entry = self._asia.get(day_start)
        if not entry or entry[2] < 6:
            return None
        return entry[0], entry[1]

    def _track_asia(self, candle: dict) -> None:
        t = candle["time"]
        if session_for(t) != "ASIAN":
            return
        day = t - t % 86400
        hi, lo, n = self._asia.get(day, (candle["high"], candle["low"], 0))
        self._asia[day] = (max(hi, candle["high"]), min(lo, candle["low"]), n + 1)
        if len(self._asia) > 400:
            for k in sorted(self._asia)[:100]:
                self._asia.pop(k, None)

    # ------------------------------------------------------------ public
    def force_scenario(self, levels: list[tuple[str, float]]) -> Optional[dict]:
        """Plant a perfect sweep of the nearest mapped level right now. Returns the plan summary."""
        if not levels:
            return None
        price = self._price
        side, level = min(levels, key=lambda x: abs(x[1] - price))
        # the level must be on the correct side of price
        if (side == "high" and level <= price) or (side == "low" and level >= price):
            candidates = [lv for lv in levels if (lv[0] == "high" and lv[1] > price) or (lv[0] == "low" and lv[1] < price)]
            if not candidates:
                return None
            side, level = min(candidates, key=lambda x: abs(x[1] - price))
        self.plan = SweepPlan(side=side, level=level, success=True, approach_len=6, depth_frac=0.55, start_price=price)  # type: ignore[arg-type]
        self.scenario_active = True
        return {"side": side, "level": level}

    def step(self) -> dict:
        """Generate and append the next 5M candle."""
        t = self._t
        sess = session_for(t)
        day_start = t - t % 86400
        self._maybe_plan(t, day_start, sess)
        if self.plan:
            candle = self._plan_candle(t)
        else:
            candle = self._random_candle(t, sess, day_start)
        self.candles.append(candle)
        self._track_asia(candle)
        if len(self.candles) > self.max_candles:
            self.candles = self.candles[-(self.max_candles - 1000):]
        self._price = candle["close"]
        self._t += FIVE_MIN
        return candle

    def spread_points(self) -> float:
        if self.instrument == "XAUUSD":
            return float(self.rng.randint(16, 30))
        return float(self.rng.randint(1200, 2400))

    # ------------------------------------------------------------ generation
    def _maybe_plan(self, t: int, day_start: int, sess: str) -> None:
        if self.plan is not None or sess not in ("LONDON", "NEW_YORK"):
            return
        key = str(day_start)
        if key not in self.day_trigger:
            self.day_trigger = {key: day_start + self.rng.randint(8 * 12, 17 * 12) * FIVE_MIN}
        if t != self.day_trigger[key]:
            return
        rng_ = self._asia_range(day_start)
        if not rng_:
            return
        hi, lo = rng_
        side = "high" if abs(self._price - hi) < abs(self._price - lo) else "low"
        level = hi if side == "high" else lo
        if (side == "high" and self._price >= level) or (side == "low" and self._price <= level):
            return
        self.plan = SweepPlan(side=side, level=level, success=self.rng.random() < 0.64, depth_frac=self.rng.random(), start_price=self._price)  # type: ignore[arg-type]

    def _volume(self, mult: float = 1.0) -> float:
        return round(self.cfg["vol_base"] * mult * self.rng.uniform(0.6, 1.4))

    def _random_candle(self, t: int, sess: str, day_start: int) -> dict:
        vol = self._abs_vol(self._price) * SESSION_VOL[sess]
        o = self._price
        drift = 0.0
        # soft mean reversion toward the Asian mid during London/NY keeps planted sweeps clean
        if sess in ("LONDON", "NEW_YORK"):
            rng_ = self._asia_range(day_start)
            if rng_:
                mid = (rng_[0] + rng_[1]) / 2
                drift = (mid - o) * 0.04
        c = o + drift + self.rng.gauss(0, vol)
        wick_up = abs(self.rng.gauss(0, vol * 0.6))
        wick_dn = abs(self.rng.gauss(0, vol * 0.6))
        h = max(o, c) + wick_up
        lo_ = min(o, c) - wick_dn
        if sess in ("LONDON", "NEW_YORK"):
            rng_ = self._asia_range(day_start)
            if rng_:
                m = self._margin(rng_[0])
                h = min(h, rng_[0] - m) if o < rng_[0] else h
                lo_ = max(lo_, rng_[1] + m) if o > rng_[1] else lo_
                c = min(max(c, lo_), h)
        return self._mk(t, o, max(h, o, c), min(lo_, o, c), c, self._volume(SESSION_VOL[sess]))

    def _mk(self, t: int, o: float, h: float, lo: float, c: float, v: float) -> dict:
        return {"time": t, "open": self._round(o), "high": self._round(h), "low": self._round(lo), "close": self._round(c), "volume": v}

    def _plan_candle(self, t: int) -> dict:
        p = self.plan
        assert p is not None
        sign = 1 if p.side == "high" else -1
        L = p.level
        m = self._margin(L)
        o = self._price
        avg = self._avg_body()
        vol = self._abs_vol(o)
        if p.phase == "approach":
            p.step += 1
            target = L - sign * m * 2
            frac = p.step / p.approach_len
            c = p.start_price + (target - p.start_price) * frac + self.rng.gauss(0, vol * 0.25)
            if sign == 1:
                c = min(c, L - m)
                h = min(max(o, c) + abs(self.rng.gauss(0, vol * 0.3)), L - m * 0.5)
                lo = min(o, c) - abs(self.rng.gauss(0, vol * 0.3))
            else:
                c = max(c, L + m)
                lo = max(min(o, c) - abs(self.rng.gauss(0, vol * 0.3)), L + m * 0.5)
                h = max(o, c) + abs(self.rng.gauss(0, vol * 0.3))
            if p.step >= p.approach_len:
                p.phase, p.step = "sweep", 0
            return self._mk(t, o, max(h, o, c), min(lo, o, c), c, self._volume())
        if p.phase == "sweep":
            depth = self._depth(L, p.depth_frac)
            extreme = L + sign * depth
            c = L - sign * m * 0.6  # closes back just inside
            h, lo = (extreme, min(o, c) - vol * 0.2) if sign == 1 else (max(o, c) + vol * 0.2, extreme)
            p.phase = "displace"
            return self._mk(t, o, h, lo, c, self._volume(2.4))
        if p.phase == "displace":
            body = max(avg * 2.6, m * 3)
            c = o - sign * body
            h = max(o, c) + vol * 0.1
            lo = min(o, c) - vol * 0.1
            if sign == 1:
                h = min(h, L - m * 0.3)
            else:
                lo = max(lo, L + m * 0.3)
            p.phase, p.step = "follow", 0
            return self._mk(t, o, max(h, o), min(lo, o), c, self._volume(2.8))
        # follow-through: reversal works (success) or price runs back through the sweep (stop hit)
        p.step += 1
        direction = -sign if p.success else sign
        c = o + direction * vol * self.rng.uniform(0.55, 1.25) + self.rng.gauss(0, vol * 0.35)
        h = max(o, c) + abs(self.rng.gauss(0, vol * 0.4))
        lo = min(o, c) - abs(self.rng.gauss(0, vol * 0.4))
        if p.step >= p.follow_len:
            p.phase = "done"
            self.plan = None
            self.scenario_active = False
        return self._mk(t, o, h, lo, c, self._volume(1.3))


class DemoFeed:
    """Holds one DemoMarket per instrument and exposes Scout-friendly accessors."""

    def __init__(self, instruments: tuple[str, ...], seed: int = 7) -> None:
        self.markets = {s: DemoMarket(s, seed=seed) for s in instruments}

    def advance(self) -> dict[str, dict]:
        return {s: m.step() for s, m in self.markets.items()}

    def candles(self, instrument: str, n: int = 2500) -> list[dict]:
        return self.markets[instrument].candles[-n:]

    def spread_points(self, instrument: str) -> float:
        return self.markets[instrument].spread_points()

    def last_price(self, instrument: str) -> float:
        return self.markets[instrument].candles[-1]["close"]
