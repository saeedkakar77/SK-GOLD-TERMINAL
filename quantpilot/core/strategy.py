"""Liquidity Sweep (stop-hunt reversal) strategy: level mapping and sweep detection.

All logic here is deterministic Python so the live engine, the backtester and the
unit tests share exactly the same rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta

import pandas as pd

from .indicators import SPECS, resample, session_for, swing_points
from .models import LiquidityLevel, Setup


@dataclass
class StrategyParams:
    """Tunable strategy thresholds (editable from Settings)."""

    xau_min_depth_pips: float = 10.0
    xau_max_depth_pips: float = 25.0
    btc_min_depth_pct: float = 0.15
    btc_max_depth_pct: float = 0.40
    displacement_mult: float = 1.2
    confirm_candles: int = 3
    xau_sl_buffer_pips: float = 5.0
    btc_sl_buffer_pct: float = 0.10
    tp1_rr: float = 2.0
    tp2_min_rr: float = 3.0
    body_lookback: int = 20
    volume_spike_mult: float = 1.5
    eq_tolerance_pips: float = 3.0
    eq_tolerance_pct: float = 0.05

    def to_dict(self) -> dict:
        return asdict(self)

    def update(self, values: dict) -> None:
        for k, v in values.items():
            if hasattr(self, k):
                cur = getattr(self, k)
                setattr(self, k, type(cur)(v))


# ---------------------------------------------------------------- Cartographer
def map_liquidity(df5: pd.DataFrame, instrument: str, params: StrategyParams | None = None) -> list[LiquidityLevel]:
    """Map liquidity pools from 5M history: PDH/PDL, Asian range, 4H swings, equal highs/lows."""
    params = params or StrategyParams()
    if len(df5) < 50:
        return []
    levels: list[LiquidityLevel] = []
    last_ts: pd.Timestamp = df5.index[-1]
    today = last_ts.normalize()

    daily = resample(df5, "1D")
    prev_days = daily[daily.index < today]
    if len(prev_days):
        pd_row = prev_days.iloc[-1]
        levels.append(LiquidityLevel(name="PDH", price=float(pd_row["high"]), side="high", strength=2))
        levels.append(LiquidityLevel(name="PDL", price=float(pd_row["low"]), side="low", strength=2))

    asia_day = today if last_ts.hour >= 7 else today - timedelta(days=1)
    asia = df5[(df5.index >= asia_day) & (df5.index < asia_day + timedelta(hours=7))]
    if len(asia) >= 6:
        levels.append(LiquidityLevel(name="ASIA_HIGH", price=float(asia["high"].max()), side="high", strength=1))
        levels.append(LiquidityLevel(name="ASIA_LOW", price=float(asia["low"].min()), side="low", strength=1))

    h4 = resample(df5, "4h")
    sh, sl = swing_points(h4, 2, 2)
    for _, p in sh[-3:]:
        levels.append(LiquidityLevel(name="SWING_4H_HIGH", price=p, side="high", strength=1))
    for _, p in sl[-3:]:
        levels.append(LiquidityLevel(name="SWING_4H_LOW", price=p, side="low", strength=1))

    m15 = resample(df5.iloc[-96 * 3 :], "15min")
    eh, el = swing_points(m15, 2, 2)
    spec = SPECS[instrument]
    ref = float(df5["close"].iloc[-1])
    tol = params.eq_tolerance_pips * spec.pip_size if instrument == "XAUUSD" else ref * params.eq_tolerance_pct / 100
    levels += _equal_clusters(eh, tol, "high")
    levels += _equal_clusters(el, tol, "low")
    return _dedupe(levels, tol)


def _equal_clusters(points: list[tuple[pd.Timestamp, float]], tol: float, side: str) -> list[LiquidityLevel]:
    out: list[LiquidityLevel] = []
    prices = sorted(p for _, p in points[-12:])
    cluster: list[float] = []
    for p in prices:
        if cluster and p - cluster[0] > tol:
            if len(cluster) >= 2:
                out.append(_eq_level(cluster, side))
            cluster = []
        cluster.append(p)
    if len(cluster) >= 2:
        out.append(_eq_level(cluster, side))
    return out


def _eq_level(cluster: list[float], side: str) -> LiquidityLevel:
    price = max(cluster) if side == "high" else min(cluster)
    return LiquidityLevel(name="EQH" if side == "high" else "EQL", price=price, side=side, strength=len(cluster))  # type: ignore[arg-type]


def _dedupe(levels: list[LiquidityLevel], tol: float) -> list[LiquidityLevel]:
    """Merge levels on the same side within tolerance, keeping the stronger / combined name."""
    out: list[LiquidityLevel] = []
    for lv in sorted(levels, key=lambda x: -x.strength):
        clash = next((o for o in out if o.side == lv.side and abs(o.price - lv.price) <= tol), None)
        if clash:
            if lv.name not in clash.name:
                clash.name = f"{clash.name}+{lv.name}"
            clash.strength += lv.strength
        else:
            out.append(lv.model_copy())
    return sorted(out, key=lambda x: x.price)


# ---------------------------------------------------------------- Hunter
def depth_in_units(instrument: str, level: float, extreme: float) -> tuple[float, str]:
    """Sweep extension beyond the level in pips (XAU) or percent (BTC)."""
    dist = abs(extreme - level)
    if instrument == "XAUUSD":
        return dist / SPECS[instrument].pip_size, "pips"
    return dist / level * 100.0, "pct"


def depth_ok(instrument: str, depth: float, params: StrategyParams) -> bool:
    if instrument == "XAUUSD":
        return params.xau_min_depth_pips <= depth <= params.xau_max_depth_pips
    return params.btc_min_depth_pct <= depth <= params.btc_max_depth_pct


def sl_buffer(instrument: str, price: float, params: StrategyParams) -> float:
    if instrument == "XAUUSD":
        return params.xau_sl_buffer_pips * SPECS[instrument].pip_size
    return price * params.btc_sl_buffer_pct / 100.0


def detect_at(
    df5: pd.DataFrame,
    i: int,
    levels: list[LiquidityLevel],
    instrument: str,
    params: StrategyParams | None = None,
) -> list[Setup]:
    """Detect sweep setups whose displacement (confirmation) candle is bar ``i``."""
    params = params or StrategyParams()
    if i < params.body_lookback + 8:
        return []
    o = df5["open"].to_numpy()
    h = df5["high"].to_numpy()
    lo = df5["low"].to_numpy()
    c = df5["close"].to_numpy()
    v = df5["volume"].to_numpy()
    t = df5["time"].to_numpy()
    bodies = abs(c[max(0, i - params.body_lookback) : i] - o[max(0, i - params.body_lookback) : i])
    avg_body = float(bodies.mean()) if len(bodies) else 1e-9
    avg_body = avg_body if avg_body > 0 else 1e-9
    avg_vol = float(v[max(0, i - params.body_lookback) : i].mean()) or 1.0
    body = abs(c[i] - o[i])
    disp_ratio = body / avg_body
    if disp_ratio < params.displacement_mult:
        return []

    setups: list[Setup] = []
    for lv in levels:
        L = lv.price
        for j in range(i, i - params.confirm_candles, -1):
            if j < 7:
                break
            if lv.side == "high":
                pierced = h[j] > L and c[j - 1] < L and h[j - 7 : j].max() <= L
                confirm = c[i] < L and c[i] < o[i]
                # earlier bars in the window must not have already confirmed (first close back inside)
                earlier = any(c[k] < L and c[k] < o[k] and abs(c[k] - o[k]) / avg_body >= params.displacement_mult for k in range(j, i))
            else:
                pierced = lo[j] < L and c[j - 1] > L and lo[j - 7 : j].min() >= L
                confirm = c[i] > L and c[i] > o[i]
                earlier = any(c[k] > L and c[k] > o[k] and abs(c[k] - o[k]) / avg_body >= params.displacement_mult for k in range(j, i))
            if not (pierced and confirm) or earlier:
                continue
            extreme = float(h[j : i + 1].max()) if lv.side == "high" else float(lo[j : i + 1].min())
            depth, unit = depth_in_units(instrument, L, extreme)
            if not depth_ok(instrument, depth, params):
                continue
            entry = float(c[i])
            buf = sl_buffer(instrument, entry, params)
            if lv.side == "high":
                direction = "SHORT"
                sl = extreme + buf
                risk = sl - entry
                tp1 = entry - params.tp1_rr * risk
                pools = sorted([x.price for x in levels if x.side == "low" and x.price < tp1], reverse=True)
                tp2 = next((p for p in pools if (entry - p) / risk >= params.tp2_min_rr), entry - params.tp2_min_rr * risk)
            else:
                direction = "LONG"
                sl = extreme - buf
                risk = entry - sl
                tp1 = entry + params.tp1_rr * risk
                pools = sorted([x.price for x in levels if x.side == "high" and x.price > tp1])
                tp2 = next((p for p in pools if (p - entry) / risk >= params.tp2_min_rr), entry + params.tp2_min_rr * risk)
            if risk <= 0:
                continue
            digits = SPECS[instrument].digits
            setups.append(
                Setup(
                    signal_id=f"{instrument}-{lv.name}-{int(t[j])}",
                    instrument=instrument,
                    direction=direction,  # type: ignore[arg-type]
                    level=lv,
                    sweep_time=int(t[j]),
                    confirm_time=int(t[i]),
                    sweep_extreme=round(extreme, digits),
                    extension_depth=round(depth, 3),
                    extension_unit=unit,  # type: ignore[arg-type]
                    displacement_ratio=round(disp_ratio, 2),
                    volume_spike=bool(max(v[j], v[i]) > params.volume_spike_mult * avg_vol),
                    entry_price=round(entry, digits),
                    stop_loss=round(sl, digits),
                    take_profit_1=round(tp1, digits),
                    take_profit_2=round(tp2, digits),
                    risk_reward_ratio=round(params.tp1_rr, 2),
                    session=session_for(int(t[i])),
                )
            )
            break  # one setup per level
    return setups


def detect_latest(df5: pd.DataFrame, instrument: str, levels: list[LiquidityLevel], params: StrategyParams | None = None) -> list[Setup]:
    """Run detection on the most recent closed candle."""
    return detect_at(df5, len(df5) - 1, levels, instrument, params)
