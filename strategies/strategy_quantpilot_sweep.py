import uuid
from typing import List, Optional
import pandas as pd

from strategies.base_strategy import BaseStrategy
from core.models import Candle, Signal
from quantpilot.core.strategy import StrategyParams, map_liquidity, detect_latest


class QuantPilotSweepStrategy(BaseStrategy):
    """
    17th Strategy: Quant Pilot 7-AI Liquidity Sweep & Displacement Stop-Hunt Reversal.
    Maps PDH/PDL, Asian High/Low, 4H Swings, and Equal Highs/Lows (EQH/EQL),
    then hunts 10-25 pip liquidity sweeps followed by >= 1.2x displacement candle close.
    """

    def __init__(self):
        super().__init__(
            "strategy_quantpilot_sweep",
            "Quant Pilot: 7-AI Liquidity Sweep & Displacement",
            "Quant Pilot core stop-hunt reversal strategy: sweeps PDH/PDL, Asian H/L, 4H Swings or EQH/EQL (10-25 pips) + >=1.2x displacement close."
        )
        self.params = StrategyParams()

    def evaluate(
        self,
        candles: List[Candle],
        symbol: str,
        timeframe: str,
        secondary_candles: Optional[List[Candle]] = None
    ) -> Optional[Signal]:
        if not candles or len(candles) < 60:
            return None

        # Only Gold (XAUUSD)
        inst = "XAUUSD"

        try:
            rows = []
            for c in candles:
                ts = pd.Timestamp(c.time)
                if ts.tzinfo is not None:
                    ts = ts.tz_convert("UTC").tz_localize(None)
                rows.append({
                    "ts": ts,
                    "time": int(ts.timestamp()),
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(getattr(c, "volume", 1.0) or 1.0),
                })

            df = pd.DataFrame(rows).set_index("ts")
            levels = map_liquidity(df, inst, self.params)
            if not levels:
                return None

            setups = detect_latest(df, inst, levels, self.params)
            if not setups:
                return None

            s = setups[0]
            action = "BUY" if s.direction == "LONG" else "SELL"
            vol_note = " | Vol Spike Confirmed" if s.volume_spike else ""
            reason = (
                f"Quant Pilot 7-AI Sweep on {s.level.name} ({s.level.price:.2f}) | "
                f"Sweep Depth: {s.extension_depth} {s.extension_unit} | "
                f"Displacement: {s.displacement_ratio}x{vol_note}"
            )

            return Signal(
                id=str(uuid.uuid4())[:8],
                strategy_id=self.strategy_id,
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action=action,
                entry_price=round(float(s.entry_price), 2),
                stop_loss=round(float(s.stop_loss), 2),
                take_profit_1=round(float(s.take_profit_1), 2),
                take_profit_2=round(float(s.take_profit_2), 2),
                reason=reason,
                timestamp=candles[-1].time.strftime("%Y-%m-%d %H:%M:%S"),
                vol_div="Quant Pilot Volume Spike" if s.volume_spike else None,
                is_ultra_strong=bool(s.volume_spike and s.displacement_ratio >= 1.5),
            )
        except Exception:
            return None
