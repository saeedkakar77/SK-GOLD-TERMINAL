from typing import List, Dict, Optional
from core.models import Candle

class VolumeDivergenceAnalyzer:
    """
    Directional Volume Smoother & Divergence Engine
    Ported directly from 'Vol Div BY SK' Pine Script.
    Computes cascaded directional WMAs (lengths 4, 4, 8, 12, 20)
    and detects Regular & Hidden Volume Divergences.
    """
    @staticmethod
    def _pine_wma_series(values: List[float], candles: List[Candle], length: int) -> List[float]:
        n = len(values)
        if n < length:
            return [0.0] * n

        result = [0.0] * n
        # Precompute weights
        weights = [(length - i) * length for i in range(length)]
        norm = sum(weights)
        if norm == 0:
            return [0.0] * n

        for idx in range(length - 1, n):
            total_sum = 0.0
            for i in range(length):
                pos = idx - i
                c = candles[pos]
                factor = -1.0 if c.close < c.open else 1.0
                total_sum += values[pos] * weights[i] * factor
            result[idx] = total_sum / norm

        # Backfill initial bars
        for idx in range(length - 1):
            result[idx] = result[length - 1]

        return result

    @classmethod
    def compute_volume_curve(cls, candles: List[Candle]) -> List[float]:
        volumes = [float(c.volume if c.volume > 0 else 100.0) for c in candles]
        
        # 5-stage Cascaded Directional WMA (lengths: 4, 4, 8, 12, 20)
        v1 = cls._pine_wma_series(volumes, candles, 4)
        v2 = cls._pine_wma_series(v1, candles, 4)
        v3 = cls._pine_wma_series(v2, candles, 8)
        v4 = cls._pine_wma_series(v3, candles, 12)
        vol_curve = cls._pine_wma_series(v4, candles, 20)
        return vol_curve

    @classmethod
    def check_divergence(cls, candles: List[Candle], max_lookback: int = 35) -> Optional[Dict]:
        """
        Scans recent 1-3 bars for Volume Divergences.
        Returns:
            dict with {
                "detected": True/False,
                "type": "Regular Bullish" / "Hidden Bullish" / "Regular Bearish" / "Hidden Bearish",
                "direction": "BUY" / "SELL",
                "is_ultra_strong": True,
                "bars_ago": int
            }
        """
        if len(candles) < 35:
            return None

        vol_curve = cls.compute_volume_curve(candles)
        
        # Check pivot points on volume curve in recent bars
        # A pivot low in vol: vol[i] < vol[i-1] and vol[i] < vol[i+1]
        vol_low_pivots = []
        vol_high_pivots = []

        for i in range(len(candles) - max_lookback, len(candles) - 1):
            if i < 1:
                continue
            if vol_curve[i] <= vol_curve[i - 1] and vol_curve[i] <= vol_curve[i + 1]:
                vol_low_pivots.append((i, vol_curve[i], candles[i].low))
            if vol_curve[i] >= vol_curve[i - 1] and vol_curve[i] >= vol_curve[i + 1]:
                vol_high_pivots.append((i, vol_curve[i], candles[i].high))

        # Check for divergence on the latest 3 bars
        curr_idx = len(candles) - 1
        curr_c = candles[-1]
        prev_c = candles[-2]

        # 🟢 Bullish Divergences (Check against last 2 low pivots)
        if len(vol_low_pivots) >= 2:
            p_last = vol_low_pivots[-1]
            p_prev = vol_low_pivots[-2]

            # Regular Bullish: Price Lower Low, Volume Higher Low
            if (curr_c.low < p_prev[2] or p_last[2] < p_prev[2]) and (p_last[1] > p_prev[1]):
                return {
                    "detected": True,
                    "type": "Regular Bullish Vol Div (Institutional Accumulation)",
                    "direction": "BUY",
                    "is_ultra_strong": True
                }

            # Hidden Bullish: Price Higher Low, Volume Lower Low
            if (curr_c.low > p_prev[2] or p_last[2] > p_prev[2]) and (p_last[1] < p_prev[1]):
                return {
                    "detected": True,
                    "type": "Hidden Bullish Vol Div (Trend Continuation)",
                    "direction": "BUY",
                    "is_ultra_strong": True
                }

        # 🔴 Bearish Divergences (Check against last 2 high pivots)
        if len(vol_high_pivots) >= 2:
            p_last = vol_high_pivots[-1]
            p_prev = vol_high_pivots[-2]

            # Regular Bearish: Price Higher High, Volume Lower High
            if (curr_c.high > p_prev[2] or p_last[2] > p_prev[2]) and (p_last[1] < p_prev[1]):
                return {
                    "detected": True,
                    "type": "Regular Bearish Vol Div (Institutional Distribution)",
                    "direction": "SELL",
                    "is_ultra_strong": True
                }

            # Hidden Bearish: Price Lower High, Volume Higher High
            if (curr_c.high < p_prev[2] or p_last[2] < p_prev[2]) and (p_last[1] > p_prev[1]):
                return {
                    "detected": True,
                    "type": "Hidden Bearish Vol Div (Trend Continuation)",
                    "direction": "SELL",
                    "is_ultra_strong": True
                }

        return None
