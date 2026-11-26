import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy
from core.volume_analyzer import VolumeDivergenceAnalyzer

class AOXModelStrategy(BaseStrategy):
    """
    Strategy 12: AOX Model (NY Midnight Expansion Zones) + MANDATORY Volume Divergence
    STRICT RULES:
    - Timeframe: Restricted strictly to M5 only.
    - Volume Divergence: 100% MANDATORY (Must be confirmed on the entry/recent candle).
    - Checks 6 SK Expansion Zones (Origin, Shift, Extreme).
    - Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_aox_model",
            name="AOX Model: NY Expansion + Vol Div (M5 Only)",
            description="NY Midnight (00:00-00:30) Expansion Zones. Strictly M5 only. Volume Divergence is 100% MANDATORY. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        # 1. Strict M5 Timeframe Check
        if timeframe.lower().strip() != "5m":
            return None

        if len(candles) < 40:
            return None

        # 2. Strict MANDATORY Volume Divergence Check
        div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
        if not div_info:
            return None  # No signal without Volume Divergence!

        curr = candles[-1]
        prev = candles[-2]

        # Calculate reference range (simulating 00:00-00:30 reference session from recent 30-min window)
        ref_bars = candles[-36:-30] if len(candles) >= 36 else candles[-12:-6]
        if not ref_bars:
            return None

        s_high = max(c.high for c in ref_bars)
        s_low  = min(c.low for c in ref_bars)
        rng    = max(s_high - s_low, 0.0001)
        base_0 = s_low

        # 3 Upper SK Zones (Resistance / Selling)
        # Origin: 2.0 - 2.5 | Shift: 3.5 - 4.0 | Extreme: 5.0 - 5.5
        up_extreme = {"top": base_0 + (5.5 * rng), "bot": base_0 + (5.0 * rng), "name": "Upper Extreme Zone (5.0-5.5)"}
        up_shift   = {"top": base_0 + (4.0 * rng), "bot": base_0 + (3.5 * rng), "name": "Upper Shift Zone (3.5-4.0)"}
        up_origin  = {"top": base_0 + (2.5 * rng), "bot": base_0 + (2.0 * rng), "name": "Upper Origin Zone (2.0-2.5)"}

        # 3 Lower SK Zones (Support / Buying)
        # Origin: -1.0 - -1.56 | Shift: -2.5 - -3.0 | Extreme: -4.0 - -4.5
        dn_origin  = {"top": base_0 - (1.0 * rng), "bot": base_0 - (1.56 * rng), "name": "Lower Origin Zone (-1.0 to -1.56)"}
        dn_shift   = {"top": base_0 - (2.5 * rng), "bot": base_0 - (3.0 * rng),  "name": "Lower Shift Zone (-2.5 to -3.0)"}
        dn_extreme = {"top": base_0 - (4.0 * rng), "bot": base_0 - (4.5 * rng),  "name": "Lower Extreme Zone (-4.0 to -4.5)"}

        candle_range = max(curr.high - curr.low, 0.0001)
        lower_wick = min(curr.open, curr.close) - curr.low
        upper_wick = curr.high - max(curr.open, curr.close)

        # 🟢 BUY EVALUATION (Lower SK Zones + Bullish Vol Div):
        if div_info["direction"] == "BUY":
            for zone in [dn_extreme, dn_shift, dn_origin]:
                top_p = zone["top"]
                bot_p = zone["bot"]
                z_name = zone["name"]

                # Retest of zone boundary
                tested = (curr.low <= top_p and curr.high >= bot_p) or (prev.low <= top_p and prev.high >= bot_p)
                # Candle body held above zone bottom (unbroken zone)
                body_held = curr.close >= bot_p and curr.open >= bot_p
                is_rejection = (curr.close > curr.open) and ((lower_wick / candle_range) >= 0.30 or curr.close > prev.high)

                if tested and body_held and is_rejection:
                    sl = bot_p - (candle_range * 0.20)
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
                            reason=f"🌟 AOX {z_name} Bounce + MANDATORY {div_info['type']} [M5 ONLY]",
                            timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S"),
                            vol_div=div_info["type"],
                            is_ultra_strong=True
                        )

        # 🔴 SELL EVALUATION (Upper SK Zones + Bearish Vol Div):
        if div_info["direction"] == "SELL":
            for zone in [up_extreme, up_shift, up_origin]:
                top_p = zone["top"]
                bot_p = zone["bot"]
                z_name = zone["name"]

                tested = (curr.high >= bot_p and curr.low <= top_p) or (prev.high >= bot_p and prev.low <= top_p)
                body_held = curr.close <= top_p and curr.open <= top_p
                is_rejection = (curr.close < curr.open) and ((upper_wick / candle_range) >= 0.30 or curr.close < prev.low)

                if tested and body_held and is_rejection:
                    sl = top_p + (candle_range * 0.20)
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
                            reason=f"🌟 AOX {z_name} Rejection + MANDATORY {div_info['type']} [M5 ONLY]",
                            timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S"),
                            vol_div=div_info["type"],
                            is_ultra_strong=True
                        )

        return None
