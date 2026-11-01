import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class DEMACrossRetestStrategy(BaseStrategy):
    """
    Strategy 9: DEMA 21 & 89 Crossover with Pullback Retest (M5 & M15 Only)
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_dema_cross_retest",
            name="DEMA 21/89 Cross & Retest (M5/M15)",
            description="DEMA 21 & 89 cross with pullback retest of DEMA 89 line. Valid only on M5 and M15. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def _calc_dema(self, values: List[float], period: int) -> List[float]:
        ema1 = self.calc_ema(values, period)
        ema2 = self.calc_ema(ema1, period)
        return [(2.0 * e1) - e2 for e1, e2 in zip(ema1, ema2)]

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if timeframe.lower() not in ["5m", "15m"]:
            return None

        if len(candles) < 130:
            return None

        closes = [c.close for c in candles]

        dema21 = self._calc_dema(closes, 21)
        dema89 = self._calc_dema(closes, 89)

        curr = candles[-1]
        prev = candles[-2]

        curr_d21 = dema21[-1]
        curr_d89 = dema89[-1]

        bullish_crossover = False
        bearish_crossover = False

        for i in range(len(candles) - 25, len(candles) - 1):
            if dema21[i] > dema89[i] and dema21[i-1] <= dema89[i-1]:
                bullish_crossover = True
            if dema21[i] < dema89[i] and dema21[i-1] >= dema89[i-1]:
                bearish_crossover = True

        candle_range = max(curr.high - curr.low, 0.0001)
        upper_wick = curr.high - max(curr.open, curr.close)
        lower_wick = min(curr.open, curr.close) - curr.low

        # 🔴 BEARISH SETUP:
        if curr_d21 < curr_d89 and (bearish_crossover or dema21[-10] < dema89[-10]):
            retested_d89 = (curr.high >= curr_d89 * 0.9995) or (prev.high >= dema89[-2] * 0.9995)
            has_rejection = (curr.close < curr.open) and (curr.close < curr_d89) and ((upper_wick / candle_range) >= 0.25 or curr.close < prev.low)

            if retested_d89 and has_rejection:
                retest_high = max(curr.high, prev.high)
                sl = retest_high + (retest_high - curr.close) * 0.15
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
                        reason=f"📉 DEMA 21/89 Bearish Cross + Red DEMA 89 Retest [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        # 🟢 BULLISH SETUP:
        if curr_d21 > curr_d89 and (bullish_crossover or dema21[-10] > dema89[-10]):
            retested_d89 = (curr.low <= curr_d89 * 1.0005) or (prev.low <= dema89[-2] * 1.0005)
            has_rejection = (curr.close > curr.open) and (curr.close > curr_d89) and ((lower_wick / candle_range) >= 0.25 or curr.close > prev.high)

            if retested_d89 and has_rejection:
                retest_low = min(curr.low, prev.low)
                sl = retest_low - (curr.close - retest_low) * 0.15
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
                        reason=f"📈 DEMA 21/89 Bullish Cross + Red DEMA 89 Retest [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        return None
