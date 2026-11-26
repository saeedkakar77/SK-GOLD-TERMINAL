import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class LiquiditySweepStrategy(BaseStrategy):
    """
    Strategy 4: Session Liquidity Sweep (Turtle Soup / Stop Hunt)
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_liquidity_sweep",
            name="Session Liquidity Sweep (Turtle Soup)",
            description="Institutions hunting retail stop losses. Triggers on session/PDH/PDL wick sweep with body close inside. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 30:
            return None

        curr = candles[-1]
        prev = candles[-2]

        lookback = min(len(candles) - 5, 40)
        session_high = max(c.high for c in candles[-lookback:-2])
        session_low = min(c.low for c in candles[-lookback:-2])

        candle_range = max(curr.high - curr.low, 0.0001)
        lower_wick = min(curr.open, curr.close) - curr.low
        upper_wick = curr.high - max(curr.open, curr.close)

        # 🟢 Bullish Liquidity Sweep Check:
        wick_swept_low = curr.low < session_low
        body_closed_above_low = curr.close > session_low and curr.open >= session_low
        has_rejection_wick = (lower_wick / candle_range) >= 0.35 or curr.close > curr.open

        if wick_swept_low and body_closed_above_low and has_rejection_wick:
            sl = curr.low - (candle_range * 0.20)
            risk = curr.close - sl
            if risk > 0:
                tp1 = round(curr.close + (risk * 1.5), 2 if "XAU" in symbol else 5)
                tp2 = round(curr.close + (risk * 3.0), 2 if "XAU" in symbol else 5)
                return Signal(
                    id=str(uuid.uuid4())[:8],
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    timeframe=timeframe,
                    action="BUY",
                    entry_price=round(curr.close, 2 if "XAU" in symbol else 5),
                    stop_loss=round(sl, 2 if "XAU" in symbol else 5),
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    reason=f"🔥 Bullish Liquidity Sweep of Low ({session_low:.2f}) + Body Inside [TP1: 1:1.5 | TP2: 1:3.0]",
                    timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                )

        # 🔴 Bearish Liquidity Sweep Check:
        wick_swept_high = curr.high > session_high
        body_closed_below_high = curr.close < session_high and curr.open <= session_high
        has_upper_wick = (upper_wick / candle_range) >= 0.35 or curr.close < curr.open

        if wick_swept_high and body_closed_below_high and has_upper_wick:
            sl = curr.high + (candle_range * 0.20)
            risk = sl - curr.close
            if risk > 0:
                tp1 = round(curr.close - (risk * 1.5), 2 if "XAU" in symbol else 5)
                tp2 = round(curr.close - (risk * 3.0), 2 if "XAU" in symbol else 5)
                return Signal(
                    id=str(uuid.uuid4())[:8],
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    timeframe=timeframe,
                    action="SELL",
                    entry_price=round(curr.close, 2 if "XAU" in symbol else 5),
                    stop_loss=round(sl, 2 if "XAU" in symbol else 5),
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    reason=f"🔥 Bearish Liquidity Sweep of High ({session_high:.2f}) + Body Inside [TP1: 1:1.5 | TP2: 1:3.0]",
                    timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                )

        return None
