import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class HTFLiquidityStrategy(BaseStrategy):
    """
    Strategy: Higher Timeframe (HTF) Major Liquidity Sweep (1H, 4H, 1D)
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_htf_liquidity",
            name="HTF Major Liquidity Sweep (1H, 4H, 1D)",
            description="Major institutional swing stop hunt on 1-Hour, 4-Hour, and Daily levels. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def _find_htf_pivots(self, candles: List[Candle], step_bars: int = 12):
        htf_highs = []
        htf_lows = []
        total = len(candles)
        
        blocks = []
        for i in range(0, total, step_bars):
            chunk = candles[i:i+step_bars]
            if len(chunk) >= 4:
                b_high = max(c.high for c in chunk)
                b_low = min(c.low for c in chunk)
                blocks.append((b_high, b_low))

        for i in range(1, len(blocks) - 1):
            if blocks[i][0] > blocks[i-1][0] and blocks[i][0] > blocks[i+1][0]:
                htf_highs.append(blocks[i][0])
            if blocks[i][1] < blocks[i-1][1] and blocks[i][1] < blocks[i+1][1]:
                htf_lows.append(blocks[i][1])

        return htf_highs, htf_lows

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 60:
            return None

        curr = candles[-1]
        prev = candles[-2]

        h1_highs, h1_lows = self._find_htf_pivots(candles[:-1], step_bars=12)
        h4_highs, h4_lows = self._find_htf_pivots(candles[:-1], step_bars=48)

        all_htf_highs = h1_highs[-3:] + h4_highs[-2:]
        all_htf_lows  = h1_lows[-3:] + h4_lows[-2:]

        candle_range = max(curr.high - curr.low, 0.0001)
        lower_wick = min(curr.open, curr.close) - curr.low
        upper_wick = curr.high - max(curr.open, curr.close)

        # 🟢 Check Bullish HTF Sweep
        for level in all_htf_lows:
            if curr.low < level and curr.close > level and curr.open >= level:
                if (lower_wick / candle_range) >= 0.35 or curr.close > curr.open:
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
                            reason=f"🌟 MAJOR HTF LIQUIDITY SWEEP of ({level:.2f}) + Rejection [TP1: 1:1.5 | TP2: 1:3.0]",
                            timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                        )

        # 🔴 Check Bearish HTF Sweep
        for level in all_htf_highs:
            if curr.high > level and curr.close < level and curr.open <= level:
                if (upper_wick / candle_range) >= 0.35 or curr.close < curr.open:
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
                            reason=f"🌟 MAJOR HTF LIQUIDITY SWEEP of ({level:.2f}) + Rejection [TP1: 1:1.5 | TP2: 1:3.0]",
                            timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                        )

        return None
