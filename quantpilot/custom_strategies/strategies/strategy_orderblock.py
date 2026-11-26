import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class OrderBlockStrategy(BaseStrategy):
    """
    Strategy 1: True Valid Order Blocks (OB) Retest & Confirmation
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_orderblock",
            name="True Order Block (OB) Retest",
            description="True OB with FVG origin. Triggers on OB test + Rejection/Engulfing confirmation candle. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 30:
            return None

        curr = candles[-1]
        prev = candles[-2]

        bullish_ob = None
        bearish_ob = None

        for i in range(10, len(candles) - 3):
            if candles[i].close > candles[i-1].high and candles[i-1].high > candles[i-2].high:
                if candles[i].low > candles[i-2].high:
                    bullish_ob = {
                        "top": candles[i-2].high,
                        "bottom": candles[i-2].low,
                        "bar_idx": i-2
                    }

            if candles[i].close < candles[i-1].low and candles[i-1].low < candles[i-2].low:
                if candles[i].high < candles[i-2].low:
                    bearish_ob = {
                        "top": candles[i-2].high,
                        "bottom": candles[i-2].low,
                        "bar_idx": i-2
                    }

        if bullish_ob:
            ob_top = bullish_ob["top"]
            ob_bot = bullish_ob["bottom"]
            tested = (curr.low <= ob_top and curr.high >= ob_bot) or (prev.low <= ob_top and prev.high >= ob_bot)
            body_intact = curr.close >= ob_bot and curr.open >= ob_bot

            candle_range = max(curr.high - curr.low, 0.0001)
            lower_wick = min(curr.open, curr.close) - curr.low
            is_pinbar = (lower_wick / candle_range) >= 0.35
            is_green_engulf = (curr.close > curr.open) and (curr.close > prev.high)

            if tested and body_intact and (is_pinbar or is_green_engulf):
                buffer = (ob_top - ob_bot) * 0.15
                sl = ob_bot - buffer
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
                        reason=f"Bullish OB Test ({ob_bot:.2f} - {ob_top:.2f}) + Confirmation [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        if bearish_ob:
            ob_top = bearish_ob["top"]
            ob_bot = bearish_ob["bottom"]
            tested = (curr.high >= ob_bot and curr.low <= ob_top) or (prev.high >= ob_bot and prev.low <= ob_top)
            body_intact = curr.close <= ob_top and curr.open <= ob_top

            candle_range = max(curr.high - curr.low, 0.0001)
            upper_wick = curr.high - max(curr.open, curr.close)
            is_shooting_star = (upper_wick / candle_range) >= 0.35
            is_red_engulf = (curr.close < curr.open) and (curr.close < prev.low)

            if tested and body_intact and (is_shooting_star or is_red_engulf):
                buffer = (ob_top - ob_bot) * 0.15
                sl = ob_top + buffer
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
                        reason=f"Bearish OB Test ({ob_bot:.2f} - {ob_top:.2f}) + Confirmation [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        return None
