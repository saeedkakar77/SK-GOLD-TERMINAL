import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy
from core.volume_analyzer import VolumeDivergenceAnalyzer

class VolumeDivergenceStrategy(BaseStrategy):
    """
    Strategy 11: Vol Div BY SK (Cascaded WMA Volume Divergence)
    Detects Regular & Hidden Volume Divergences.
    Also acts as universal confluence filter for all other strategies.
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_volume_divergence",
            name="Vol Div: Institutional Volume Flow",
            description="5-Stage Cascaded WMA Directional Volume Divergence. Acts as universal strength multiplier for all strategies. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
        if not div_info:
            return None

        curr = candles[-1]
        prev = candles[-2]
        candle_range = max(curr.high - curr.low, 0.0001)

        action = div_info["direction"]
        div_type = div_info["type"]

        if action == "BUY":
            # Confirmation: green close or rejection lower wick
            is_confirmed = (curr.close > curr.open) or (curr.close > prev.close)
            if is_confirmed:
                sl = curr.low - (candle_range * 0.25)
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
                        reason=f"📊 {div_type} Confirmed on {timeframe.upper()}",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_type,
                        is_ultra_strong=True
                    )

        elif action == "SELL":
            is_confirmed = (curr.close < curr.open) or (curr.close < prev.close)
            if is_confirmed:
                sl = curr.high + (candle_range * 0.25)
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
                        reason=f"📊 {div_type} Confirmed on {timeframe.upper()}",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_type,
                        is_ultra_strong=True
                    )

        return None
