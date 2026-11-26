"""Deterministic market-structure helpers: instrument specs, sessions, swings, resampling."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class InstrumentSpec:
    """Static contract details used for sizing and strategy thresholds."""

    symbol: str
    pip_size: float  # price units per pip
    point: float  # price units per broker point
    contract_size: float  # units per 1.0 lot
    volume_min: float
    volume_step: float
    volume_max: float
    digits: int
    sessions_matter: bool


SPECS: dict[str, InstrumentSpec] = {
    # Gold: 1 pip = $0.10, 1 point = $0.01, 1 lot = 100 oz
    "XAUUSD": InstrumentSpec("XAUUSD", 0.10, 0.01, 100.0, 0.01, 0.01, 50.0, 2, True),
    # Bitcoin CFD: 1 lot = 1 BTC
    "BTCUSD": InstrumentSpec("BTCUSD", 1.0, 0.01, 1.0, 0.01, 0.01, 20.0, 2, False),
}

# Session windows in UTC hours [start, end)
SESSIONS_UTC: dict[str, tuple[int, int]] = {
    "ASIAN": (0, 7),
    "LONDON": (7, 12),
    "NEW_YORK": (12, 21),
}
IST_OFFSET_MIN = 330


def session_for(ts: int | float | datetime) -> str:
    """Return the trading session name for a UTC unix timestamp or datetime."""
    dt = ts if isinstance(ts, datetime) else datetime.fromtimestamp(float(ts), tz=timezone.utc)
    h = dt.hour
    for name, (start, end) in SESSIONS_UTC.items():
        if start <= h < end:
            return name
    return "OFF_HOURS"


def session_info(now: datetime | None = None) -> dict:
    """Session badge data: current session, UTC/IST clocks and day progress 0..1 for the arc."""
    now = now or datetime.now(timezone.utc)
    ist_minutes = (now.hour * 60 + now.minute + IST_OFFSET_MIN) % (24 * 60)
    return {
        "session": session_for(now),
        "utc": now.strftime("%H:%M"),
        "ist": f"{ist_minutes // 60:02d}:{ist_minutes % 60:02d}",
        "day_progress": (now.hour * 60 + now.minute) / 1440.0,
        "windows_utc": SESSIONS_UTC,
    }


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample an OHLCV frame (index = UTC DatetimeIndex) to a higher timeframe."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = df.resample(rule, label="left", closed="left").agg(agg).dropna()
    return out


def swing_points(df: pd.DataFrame, left: int = 2, right: int = 2) -> tuple[list[tuple[pd.Timestamp, float]], list[tuple[pd.Timestamp, float]]]:
    """Fractal swing highs/lows: a bar whose high (low) is the extreme of left+right neighbours."""
    highs: list[tuple[pd.Timestamp, float]] = []
    lows: list[tuple[pd.Timestamp, float]] = []
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    idx = df.index
    for i in range(left, len(df) - right):
        window_h = h[i - left : i + right + 1]
        window_l = lo[i - left : i + right + 1]
        if h[i] == window_h.max() and np.sum(window_h == h[i]) == 1:
            highs.append((idx[i], float(h[i])))
        if lo[i] == window_l.min() and np.sum(window_l == lo[i]) == 1:
            lows.append((idx[i], float(lo[i])))
    return highs, lows


def average_body(df: pd.DataFrame, lookback: int = 20) -> float:
    """Mean absolute candle body over the lookback window (excluding the latest candle)."""
    bodies = (df["close"] - df["open"]).abs()
    window = bodies.iloc[-lookback - 1 : -1] if len(bodies) > lookback else bodies.iloc[:-1]
    val = float(window.mean()) if len(window) else float(bodies.mean())
    return val if val > 0 else 1e-9


def to_frame(candles: list[dict]) -> pd.DataFrame:
    """Convert a list of {time, open, high, low, close, volume} dicts to a UTC-indexed frame."""
    df = pd.DataFrame(candles)
    df.index = pd.to_datetime(df["time"], unit="s", utc=True)
    return df[["time", "open", "high", "low", "close", "volume"]]
