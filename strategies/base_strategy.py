from abc import ABC, abstractmethod
from typing import List, Optional
from core.models import Candle, Signal

class BaseStrategy(ABC):
    def __init__(self, strategy_id: str, name: str, description: str):
        self.strategy_id = strategy_id
        self.name = name
        self.description = description
        self.enabled = True

    @abstractmethod
    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        """
        Takes recent candle bars (ordered chronologically, newest last)
        and returns a Signal if rules are satisfied, else None.
        """
        pass

    @staticmethod
    def calc_ema(values: List[float], period: int) -> List[float]:
        if not values or len(values) < period:
            return [0.0] * len(values)
        ema = [0.0] * len(values)
        k = 2.0 / (period + 1.0)
        # Seed with SMA of first period elements
        sma = sum(values[:period]) / period
        ema[period - 1] = sma
        for i in range(period, len(values)):
            ema[i] = (values[i] * k) + (ema[i - 1] * (1.0 - k))
        # Fill earlier points
        for i in range(period - 1):
            ema[i] = values[i]
        return ema

    @staticmethod
    def calc_atr(candles: List[Candle], period: int = 14) -> List[float]:
        if len(candles) < 2:
            return [0.0] * len(candles)
        tr = [0.0] * len(candles)
        tr[0] = candles[0].high - candles[0].low
        for i in range(1, len(candles)):
            hl = candles[i].high - candles[i].low
            hc = abs(candles[i].high - candles[i - 1].close)
            lc = abs(candles[i].low - candles[i - 1].close)
            tr[i] = max(hl, hc, lc)
        
        atr = [0.0] * len(candles)
        if len(tr) >= period:
            atr[period - 1] = sum(tr[:period]) / period
            for i in range(period, len(candles)):
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr
