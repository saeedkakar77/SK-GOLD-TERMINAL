"""Strategy Manager for SK PILOT: Loads, toggles and evaluates the 17 institutional backup strategies."""
from __future__ import annotations

import datetime
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

# Ensure strategies and core are accessible
_STRAT_DIR = Path(__file__).resolve().parent
if str(_STRAT_DIR) not in sys.path:
    sys.path.insert(0, str(_STRAT_DIR))

import strategies
from core.models import Candle
from backend.core.models import LiquidityLevel, Setup
from backend.core.indicators import session_for

log = logging.getLogger("quantpilot.strategies")

CATEGORY_MAP = {
    "strategy_breaker_ifvg_unicorn": "ICT Unicorn",
    "strategy_orderblock": "Smart Money (SMC)",
    "strategy_fvg": "Fair Value Gap",
    "strategy_smt": "SMT Divergence",
    "strategy_liquidity_sweep": "Turtle Soup Sweep",
    "strategy_idm_structure": "IDM Structure",
    "strategy_smc_structure_idm_ext": "SMC Structure EXT",
    "strategy_bbma_multi_tf": "BBMA Multi-TF",
    "strategy_ao_model": "AOX Expansion",
    "strategy_aox_model": "AOX Expansion",
    "strategy_crt_model": "CRT Multi-TF",
    "strategy_ef_engulfing_fail": "Engulfing Failure",
    "strategy_msnr_snr": "MSNR Levels",
    "strategy_volume_divergence": "Volume Flow",
    "strategy_htf_liquidity": "HTF Liquidity",
    "strategy_ema_ribbon": "Trend Ribbon",
    "strategy_dema_cross_retest": "Momentum DEMA",
    "strategy_cme_open_interest": "CME Institutional",
    "strategy_default_sweep": "Core SMC Sweep",
}


class StrategyManager:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.strategies: dict[str, Any] = {}
        self._load_all_strategies()
        # Load saved toggles from database, default to all enabled
        saved = self.db.kv_get("strategy_toggles", {}) or {}
        self.toggles: dict[str, bool] = {}
        for s_id in self.strategies:
            self.toggles[s_id] = saved.get(s_id, True)
        self.toggles["strategy_default_sweep"] = saved.get("strategy_default_sweep", True)

    def _load_all_strategies(self) -> None:
        for name in getattr(strategies, "__all__", []):
            if name == "BaseStrategy":
                continue
            try:
                cls = getattr(strategies, name)
                instance = cls()
                self.strategies[instance.strategy_id] = instance
                log.info("Loaded strategy: %s (%s)", instance.strategy_id, instance.name)
            except Exception as e:
                log.warning("Could not load strategy %s: %s", name, e)

    def get_strategies_list(self) -> list[dict[str, Any]]:
        result = []
        for s_id, s in self.strategies.items():
            result.append({
                "id": s_id,
                "name": s.name,
                "description": getattr(s, "description", ""),
                "category": CATEGORY_MAP.get(s_id, "SMC / Price Action"),
                "enabled": self.toggles.get(s_id, True),
            })
        # Add default sweep as well
        result.append({
            "id": "strategy_default_sweep",
            "name": "7-Agent Liquidity Sweep (Original)",
            "description": "Scans EQH, EQL, PDH, PDL and Asian range sweeps with displacement reversal.",
            "category": "Core SMC Sweep",
            "enabled": self.toggles.get("strategy_default_sweep", True),
        })
        return result

    def set_toggle(self, strategy_id: str, enabled: bool) -> dict[str, Any]:
        self.toggles[strategy_id] = bool(enabled)
        self.db.kv_set("strategy_toggles", self.toggles)
        return {"ok": True, "strategy_id": strategy_id, "enabled": self.toggles[strategy_id]}

    def set_toggle_all(self, enabled: bool) -> dict[str, Any]:
        val = bool(enabled)
        for s_id in self.toggles:
            self.toggles[s_id] = val
        self.db.kv_set("strategy_toggles", self.toggles)
        return {"ok": True, "enabled_all": val}

    def is_enabled(self, strategy_id: str) -> bool:
        return self.toggles.get(strategy_id, True)

    def evaluate_candles(self, candles: list[dict], instrument: str) -> Optional[Setup]:
        """Runs all enabled custom strategies against the current candle history."""
        if not candles or len(candles) < 30:
            return None

        # Convert dict candles to Candle dataclass
        c_objs: list[Candle] = []
        for c in candles:
            raw_t = c.get("time") or 0
            if isinstance(raw_t, datetime.datetime):
                dt = raw_t
            else:
                try:
                    dt = datetime.datetime.fromtimestamp(float(raw_t), tz=datetime.timezone.utc)
                except Exception:
                    dt = datetime.datetime.now(datetime.timezone.utc)

            c_objs.append(Candle(
                time=dt,
                open=float(c.get("open", 0.0)),
                high=float(c.get("high", 0.0)),
                low=float(c.get("low", 0.0)),
                close=float(c.get("close", 0.0)),
                volume=float(c.get("volume", 0.0)),
            ))

        # Check each enabled custom strategy
        for s_id, strat in self.strategies.items():
            if not self.is_enabled(s_id):
                continue
            try:
                sig = strat.evaluate(c_objs, instrument, "M5")
                if sig and getattr(sig, "action", None) in ("BUY", "SELL"):
                    direction = "LONG" if sig.action == "BUY" else "SHORT"
                    entry = float(sig.entry_price)
                    sl = float(sig.stop_loss)
                    tp1 = float(sig.take_profit_1)
                    tp2 = float(sig.take_profit_2)
                    risk = abs(entry - sl)
                    if risk <= 0:
                        continue
                    rr = round(abs(tp1 - entry) / risk, 2)
                    last_c = candles[-1]
                    raw_lc = last_c.get("time")
                    if isinstance(raw_lc, datetime.datetime):
                        t_now = int(raw_lc.timestamp())
                    elif raw_lc:
                        t_now = int(float(raw_lc))
                    else:
                        t_now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                    unit = "pips" if "XAU" in instrument else "pct"
                    depth = round(risk / 0.1, 1) if unit == "pips" else round(risk / max(entry, 1.0) * 100, 2)

                    setup = Setup(
                        signal_id=uuid.uuid4().hex[:12],
                        instrument=instrument,
                        direction=direction,
                        level=LiquidityLevel(
                            name=f"{strat.name[:24]}",
                            price=sl,
                            side="low" if direction == "LONG" else "high",
                            strength=3,
                        ),
                        sweep_time=t_now,
                        confirm_time=t_now,
                        sweep_extreme=sl,
                        extension_depth=depth,
                        extension_unit=unit,
                        displacement_ratio=1.5,
                        volume_spike=True,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        risk_reward_ratio=rr,
                        session=session_for(t_now),
                    )
                    log.info("Custom strategy triggered: %s [%s] @ %s (SL: %s TP1: %s)", strat.name, direction, entry, sl, tp1)
                    return setup
            except Exception as e:
                log.warning("Strategy evaluation error (%s): %s", s_id, e)

        return None
