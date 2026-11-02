from typing import List, Optional, Dict
from core.models import Candle

class ConfirmationAnalyzer:
    """
    Universal Institutional Candlestick Confirmation Engine
    Strictly trained on user's 10 Confirmation Architecture Diagrams:
    
    1. 2-Candle Confirmation (BUY):
       - C1: Bearish dip into key level
       - C2: Strong Bullish Engulfing OR Piercing Line OR Low-Sweep with Long Lower Rejection Wick.
       
    2. 3-Candle Confirmation (BUY):
       - C1: Bearish drop candle
       - C2: Small pause / indecision / liquidity absorption candle
       - C3: Strong Bullish expansion candle closing above C1 midpoint and above C2 high.
       
    3. 2-Candle Confirmation (SELL):
       - C1: Bullish push into key level
       - C2: Strong Bearish Engulfing OR Dark Cloud Cover OR High-Sweep with Long Upper Rejection Wick.
       
    4. 3-Candle Confirmation (SELL):
       - C1: Bullish expansion candle
       - C2: Small pause / indecision / liquidity sweep candle
       - C3: Strong Bearish expansion candle closing below C1 midpoint and below C2 low.
    """

    @staticmethod
    def check_bullish_confirmation(candles: List[Candle]) -> Optional[Dict[str, str]]:
        if len(candles) < 3:
            return None

        c3 = candles[-1] # Current trigger closed candle
        c2 = candles[-2] # Previous closed candle
        c1 = candles[-3] # 2 bars ago

        # -------------------------------------------------------------
        # 1. Check 2-Candle Bullish Confirmation (c2 & c3)
        # -------------------------------------------------------------
        c2_body = abs(c2.close - c2.open)
        c3_body = abs(c3.close - c3.open)
        c3_range = max(c3.high - c3.low, 0.001)
        c3_lower_wick = min(c3.open, c3.close) - c3.low

        is_c2_bearish = c2.close < c2.open or (c2.close <= c2.open and c2_body < 0.001)
        is_c3_bullish = c3.close > c3.open

        if is_c3_bullish:
            # Type A: Full Bullish Engulfing
            if is_c2_bearish and c3.close >= c2.open and c3.open <= c2.close:
                return {
                    "type": "2-Candle Bullish Confirmation (Full Bullish Engulfing)",
                    "pattern": "2-Candle Engulfing",
                    "details": f"Bullish body completely engulfs previous bearish candle ({c3.close:.2f} >= {c2.open:.2f})"
                }

            # Type B: Piercing Line (Closes > 50% of previous bearish candle)
            c2_mid = (c2.open + c2.close) / 2.0
            if is_c2_bearish and c3.close > c2_mid and c3.close > c2.close:
                return {
                    "type": "2-Candle Bullish Confirmation (Piercing Reversal)",
                    "pattern": "2-Candle Piercing",
                    "details": f"Bullish candle reclaims >50% of prior drop ({c3.close:.2f} > {c2_mid:.2f})"
                }

            # Type C: Liquidity Sweep + Strong Lower Wick Rejection (Hammer/Pinbar)
            if (c3_lower_wick / c3_range) >= 0.35 and c3.close >= c2.close:
                return {
                    "type": "2-Candle Bullish Confirmation (Liquidity Sweep + Lower Wick Rejection)",
                    "pattern": "Wick Sweep Rejection",
                    "details": f"Lower rejection wick absorbs liquidity ({c3_lower_wick/c3_range*100:.0f}% wick)"
                }

        # -------------------------------------------------------------
        # 2. Check 3-Candle Bullish Confirmation (c1, c2, c3 - Morning Star)
        # -------------------------------------------------------------
        is_c1_bearish = c1.close < c1.open
        c1_mid = (c1.open + c1.close) / 2.0
        c1_range = max(c1.high - c1.low, 0.001)

        # C2 must be an indecision / small body pause candle
        is_c2_small = (c2_body <= c1_range * 0.65)

        if is_c1_bearish and is_c2_small and is_c3_bullish:
            if c3.close > c1_mid and c3.close > c2.high:
                return {
                    "type": "3-Candle Bullish Confirmation (Morning Star / Liquidity Absorption)",
                    "pattern": "3-Candle Morning Star",
                    "details": f"C1 drop -> C2 pause ({c2.low:.2f}) -> C3 bullish impulse close ({c3.close:.2f})"
                }

        # Type D: Single-Candle Pinbar Reversal
        if (c3_lower_wick / c3_range) >= 0.40 and c3.close >= c3.open:
            return {
                "type": "Bullish Pinbar Liquidity Absorption",
                "pattern": "Bullish Pinbar",
                "details": f"Massive lower rejection wick ({c3_lower_wick/c3_range*100:.0f}%) absorbs buy-side liquidity"
            }

        return None

    @staticmethod
    def check_bearish_confirmation(candles: List[Candle]) -> Optional[Dict[str, str]]:
        if len(candles) < 3:
            return None

        c3 = candles[-1] # Current trigger closed candle
        c2 = candles[-2] # Previous closed candle
        c1 = candles[-3] # 2 bars ago

        # -------------------------------------------------------------
        # 1. Check 2-Candle Bearish Confirmation (c2 & c3)
        # -------------------------------------------------------------
        c2_body = abs(c2.close - c2.open)
        c3_body = abs(c3.close - c3.open)
        c3_range = max(c3.high - c3.low, 0.001)
        c3_upper_wick = c3.high - max(c3.open, c3.close)

        is_c2_bullish = c2.close > c2.open or (c2.close >= c2.open and c2_body < 0.001)
        is_c3_bearish = c3.close < c3.open

        if is_c3_bearish:
            # Type A: Full Bearish Engulfing
            if is_c2_bullish and c3.close <= c2.open and c3.open >= c2.close:
                return {
                    "type": "2-Candle Bearish Confirmation (Full Bearish Engulfing)",
                    "pattern": "2-Candle Engulfing",
                    "details": f"Bearish body completely engulfs previous bullish candle ({c3.close:.2f} <= {c2.open:.2f})"
                }

            # Type B: Dark Cloud Cover (Closes < 50% of previous bullish candle)
            c2_mid = (c2.open + c2.close) / 2.0
            if is_c2_bullish and c3.close < c2_mid and c3.close < c2.close:
                return {
                    "type": "2-Candle Bearish Confirmation (Dark Cloud Cover)",
                    "pattern": "2-Candle Dark Cloud",
                    "details": f"Bearish candle reclaims >50% of prior push ({c3.close:.2f} < {c2_mid:.2f})"
                }

            # Type C: Liquidity Sweep + Strong Upper Wick Rejection (Shooting Star/Pinbar)
            if (c3_upper_wick / c3_range) >= 0.35 and c3.close <= c2.close:
                return {
                    "type": "2-Candle Bearish Confirmation (Liquidity Sweep + Upper Wick Rejection)",
                    "pattern": "Wick Sweep Rejection",
                    "details": f"Upper rejection wick absorbs buy liquidity ({c3_upper_wick/c3_range*100:.0f}% wick)"
                }

        # -------------------------------------------------------------
        # 2. Check 3-Candle Bearish Confirmation (c1, c2, c3 - Evening Star)
        # -------------------------------------------------------------
        is_c1_bullish = c1.close > c1.open
        c1_mid = (c1.open + c1.close) / 2.0
        c1_range = max(c1.high - c1.low, 0.001)

        # C2 must be an indecision / small body pause candle
        is_c2_small = (c2_body <= c1_range * 0.65)

        if is_c1_bullish and is_c2_small and is_c3_bearish:
            if c3.close < c1_mid and c3.close < c2.low:
                return {
                    "type": "3-Candle Bearish Confirmation (Evening Star / Liquidity Absorption)",
                    "pattern": "3-Candle Evening Star",
                    "details": f"C1 push -> C2 pause ({c2.high:.2f}) -> C3 bearish impulse close ({c3.close:.2f})"
                }

        # Type D: Single-Candle Pinbar Rejection
        if (c3_upper_wick / c3_range) >= 0.40 and c3.close <= c3.open:
            return {
                "type": "Bearish Pinbar Liquidity Rejection",
                "pattern": "Bearish Pinbar",
                "details": f"Massive upper rejection wick ({c3_upper_wick/c3_range*100:.0f}%) rejects premium liquidity"
            }

        return None

    @classmethod
    def analyze_signal_confluence(cls, candles: List[Candle], action: str, vol_div: Optional[str] = None, htf_bias: Optional[str] = None) -> Dict:
        """
        Scans and scores candlestick confirmation patterns strictly trained on user's diagrams.
        Computes accurate confluence percentage score (%):
          - Base Strategy Trigger: 50%
          - Candlestick Confirmation Pattern (2-Candle / 3-Candle): +25%
          - Institutional Volume Divergence: +15%
          - HTF Master Trend Alignment (Weekly/Daily/H4): +10%
        Total: Up to 100%
        """
        score = 50
        pattern_info = cls.check_bullish_confirmation(candles) if action == "BUY" else cls.check_bearish_confirmation(candles)

        if pattern_info:
            score += 25
            pattern_name = pattern_info["type"]
            pattern_details = pattern_info["details"]
        else:
            curr = candles[-1]
            prev = candles[-2]
            rng = max(curr.high - curr.low, 0.001)
            # Check secondary rejection wick
            if action == "BUY":
                wick = min(curr.open, curr.close) - curr.low
                if (wick / rng) >= 0.28:
                    score += 15
                    pattern_name = "Bullish Rejection Wick (Demand Absorption)"
                    pattern_details = f"Closed with {wick/rng*100:.0f}% lower absorption wick"
                else:
                    pattern_name = "Closed Candle Momentum (Standard)"
                    pattern_details = "Confirmed upon bar close without multi-candle pattern"
            else:
                wick = curr.high - max(curr.open, curr.close)
                if (wick / rng) >= 0.28:
                    score += 15
                    pattern_name = "Bearish Rejection Wick (Supply Rejection)"
                    pattern_details = f"Closed with {wick/rng*100:.0f}% upper rejection wick"
                else:
                    pattern_name = "Closed Candle Momentum (Standard)"
                    pattern_details = "Confirmed upon bar close without multi-candle pattern"

        if vol_div:
            score += 15

        if htf_bias:
            bias_upper = htf_bias.upper()
            if (action == "BUY" and "BUY" in bias_upper) or (action == "SELL" and "SELL" in bias_upper):
                score += 10
            elif (action == "BUY" and "SELL" in bias_upper) or (action == "SELL" and "BUY" in bias_upper):
                score = max(35, score - 15)  # Counter-trend penalty

        score = min(score, 100)

        if score >= 90:
            strength = "A+ ULTRA STRONG"
            badge_color = "#10b981"
            badge_emoji = "🔥"
        elif score >= 75:
            strength = "STRONG"
            badge_color = "#3b82f6"
            badge_emoji = "⚡"
        elif score >= 60:
            strength = "MODERATE"
            badge_color = "#f59e0b"
            badge_emoji = "⚖️"
        else:
            strength = "WEAK"
            badge_color = "#ef4444"
            badge_emoji = "⚠️"

        return {
            "score_pct": score,
            "strength": strength,
            "pattern_name": pattern_name,
            "pattern_details": pattern_details,
            "badge_color": badge_color,
            "badge_emoji": badge_emoji
        }
