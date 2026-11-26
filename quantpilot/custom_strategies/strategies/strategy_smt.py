import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class SMTStrategy(BaseStrategy):
    """
    Strategy 3: SMT Divergence Strategy (Smart Money Tool)
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_smt",
            name="SMT Divergence (Correlated Assets)",
            description="Institutional divergence between Gold & Silver/DXY. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def _find_pivots(self, candles: List[Candle], lookback: int = 3):
        highs = []
        lows = []
        for i in range(lookback, len(candles) - lookback):
            is_ph = True
            for k in range(1, lookback + 1):
                if candles[i].high <= candles[i - k].high or candles[i].high < candles[i + k].high:
                    is_ph = False
                    break
            if is_ph:
                highs.append((i, candles[i].high))

            is_pl = True
            for k in range(1, lookback + 1):
                if candles[i].low >= candles[i - k].low or candles[i].low > candles[i + k].low:
                    is_pl = False
                    break
            if is_pl:
                lows.append((i, candles[i].low))

        return highs, lows

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 25:
            return None

        curr = candles[-1]
        prev = candles[-2]

        p1_highs, p1_lows = self._find_pivots(candles, lookback=3)

        if secondary_candles and len(secondary_candles) >= 25:
            p2_highs, p2_lows = self._find_pivots(secondary_candles, lookback=3)

            # Check Bullish SMT
            if len(p1_lows) >= 2 and len(p2_lows) >= 2:
                last_p1 = p1_lows[-1]
                prev_p1 = p1_lows[-2]
                last_p2 = p2_lows[-1]
                prev_p2 = p2_lows[-2]

                if last_p1[1] < prev_p1[1] and last_p2[1] > prev_p2[1]:
                    if curr.close > curr.open and curr.close > prev.high:
                        sl = last_p1[1] - (curr.close - last_p1[1]) * 0.2
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
                                reason="🟢 Bullish SMT Divergence + MSS Close [TP1: 1:1.5 | TP2: 1:3.0]",
                                timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                            )

            # Check Bearish SMT
            if len(p1_highs) >= 2 and len(p2_highs) >= 2:
                last_p1 = p1_highs[-1]
                prev_p1 = p1_highs[-2]
                last_p2 = p2_highs[-1]
                prev_p2 = p2_highs[-2]

                if last_p1[1] > prev_p1[1] and last_p2[1] < prev_p2[1]:
                    if curr.close < curr.open and curr.close < prev.low:
                        sl = last_p1[1] + (last_p1[1] - curr.close) * 0.2
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
                                reason="🔴 Bearish SMT Divergence + MSS Close [TP1: 1:1.5 | TP2: 1:3.0]",
                                timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                            )
        else:
            if len(p1_lows) >= 2:
                last_low = p1_lows[-1]
                prev_low = p1_lows[-2]
                if last_low[1] < prev_low[1]:
                    lower_wick = min(curr.open, curr.close) - curr.low
                    candle_range = max(curr.high - curr.low, 0.0001)
                    if (lower_wick / candle_range) >= 0.40 and curr.close > curr.open:
                        sl = curr.low - (curr.close - curr.low) * 0.25
                        risk = curr.close - sl
                        if risk > 0:
                            return Signal(
                                id=str(uuid.uuid4())[:8],
                                strategy_id=self.strategy_id,
                                strategy_name=self.name,
                                symbol=symbol,
                                timeframe=timeframe,
                                action="BUY",
                                entry_price=round(curr.close, 2 if "XAU" in symbol else 5),
                                stop_loss=round(sl, 2 if "XAU" in symbol else 5),
                                take_profit_1=round(curr.close + (risk * 1.5), 2 if "XAU" in symbol else 5),
                                take_profit_2=round(curr.close + (risk * 3.0), 2 if "XAU" in symbol else 5),
                                reason="🟢 Standalone SMT Pivot Reversal Pinbar [TP1: 1:1.5 | TP2: 1:3.0]",
                                timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                            )

        return None
