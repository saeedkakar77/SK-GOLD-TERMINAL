import uuid
import datetime
from typing import List, Optional, Tuple, Dict
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy
from core.volume_analyzer import VolumeDivergenceAnalyzer

class CRTModelStrategy(BaseStrategy):
    """
    Strategy 13: CRT SETUP BY SK (Candle Range Theory C1-C2-C3 Fractal Model)
    STRICT USER RULES:
    1. Exact Multi-Timeframe Pairing:
       - H1 CRT -> Signals on M5
       - H4 CRT -> Signals on M15
       - Daily (1D) CRT -> Signals on H1
       - Weekly (1W) CRT -> Signals on H4
       - Monthly (1M) CRT -> Signals on Daily (1D)
    2. 3 Distinct Entry Models (Tagged by Strength):
       - Type 2: ⭐ A+ PRO SNIPER (First Presented FVG) [Strongest!]
       - Type 3: 🎯 C2 WICK 50% EQ RETEST
       - Type 1: ⚡ DIRECT C3 OPEN ENTRY
    3. Volume Divergence is 100% MANDATORY.
    4. Fixed Targets: TP1 = 1:1.5 RR | TP2 = 1:3.0 RR.
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_crt_model",
            name="CRT Setup: C1-C2-C3 Multi-TF + Vol Div",
            description="Candle Range Theory (H1->M5, H4->M15, 1D->H1, 1W->H4, 1M->1D) with First FVG Sniper, EQ Retest & Mandatory Vol Div. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def _get_htf_params(self, ltf: str) -> Optional[Tuple[str, int]]:
        """Maps LTF execution timeframe to parent HTF and required chunk step."""
        ltf_clean = ltf.lower().strip()
        mapping = {
            "5m":  ("1h", 12),    # 12 bars of 5m = 1 hour
            "15m": ("4h", 16),    # 16 bars of 15m = 4 hours
            "1h":  ("1d", 24),    # 24 bars of 1h = 1 day
            "4h":  ("1w", 30),    # ~30 bars of 4h = 1 week
            "1d":  ("1m_month", 22) # ~22 trading days = 1 month
        }
        return mapping.get(ltf_clean)

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        params = self._get_htf_params(timeframe)
        if not params:
            return None  # Only evaluate on the designated execution timeframes (M5, M15, H1, H4, 1D)

        htf_name, step = params

        # Need at least 3 full HTF blocks
        if len(candles) < step * 3:
            return None

        # 1. MANDATORY Volume Divergence Check
        div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
        if not div_info:
            return None  # Vol Div is MUST!

        # 2. Build HTF Candles (C1, C2, and current C3)
        # C1 is the HTF bar before C2
        c1_bars = candles[-(step * 3):-(step * 2)]
        c2_bars = candles[-(step * 2):-step]
        c3_bars = candles[-step:]

        if not c1_bars or not c2_bars:
            return None

        c1_high  = max(c.high for c in c1_bars)
        c1_low   = min(c.low for c in c1_bars)
        c1_open  = c1_bars[0].open
        c1_close = c1_bars[-1].close

        c2_high  = max(c.high for c in c2_bars)
        c2_low   = min(c.low for c in c2_bars)
        c2_open  = c2_bars[0].open
        c2_close = c2_bars[-1].close

        curr = candles[-1]
        prev = candles[-2]
        candle_range = max(curr.high - curr.low, 0.0001)

        # 3. Check C1 vs C2 Sweep Mechanics
        # Bullish CRT: C2 swept C1 Low, but closed back ABOVE C1 Low
        bullish_crt = (c2_low < c1_low) and (c2_close >= c1_low)

        # Bearish CRT: C2 swept C1 High, but closed back BELOW C1 High
        bearish_crt = (c2_high > c1_high) and (c2_close <= c1_high)

        # ----------------------------------------------------
        # 🟢 BULLISH CRT MODEL (BUY)
        # ----------------------------------------------------
        if bullish_crt and div_info["direction"] == "BUY":
            # Detect Entry Type:
            entry_type = None

            # Type 2: First Presented FVG (Strongest!)
            first_fvg_top = None
            first_fvg_bot = None
            for i in range(len(candles) - step, len(candles) - 1):
                if i >= 2 and candles[i].low > candles[i-2].high:
                    first_fvg_top = candles[i].low
                    first_fvg_bot = candles[i-2].high
                    break

            if first_fvg_top and first_fvg_bot:
                if curr.low <= first_fvg_top and curr.high >= first_fvg_bot and curr.close > curr.open:
                    entry_type = "⭐ A+ PRO SNIPER (First Presented FVG Retest)"

            # Type 3: C2 Lower Wick 50% Equilibrium Retest
            c2_wick_eq = (c2_low + min(c2_open, c2_close)) / 2.0
            if not entry_type and curr.low <= c2_wick_eq * 1.0005 and curr.close > curr.open:
                entry_type = "🎯 C2 WICK 50% EQ RETEST"

            # Type 1: Direct C3 Open Entry
            if not entry_type and len(c3_bars) <= 3 and curr.close > curr.open:
                entry_type = "⚡ DIRECT C3 OPEN ENTRY"

            if entry_type:
                sl = c2_low - (candle_range * 0.20)
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
                        reason=f"🔥 CRT [{htf_name.upper()} -> {timeframe.upper()}] Bullish C2 Sweep ({c1_low:.2f}) | {entry_type} + MANDATORY {div_info['type']}",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_info["type"],
                        is_ultra_strong=True
                    )

        # ----------------------------------------------------
        # 🔴 BEARISH CRT MODEL (SELL)
        # ----------------------------------------------------
        if bearish_crt and div_info["direction"] == "SELL":
            entry_type = None

            # Type 2: First Presented Bearish FVG (Strongest!)
            first_fvg_top = None
            first_fvg_bot = None
            for i in range(len(candles) - step, len(candles) - 1):
                if i >= 2 and candles[i].high < candles[i-2].low:
                    first_fvg_top = candles[i-2].low
                    first_fvg_bot = candles[i].high
                    break

            if first_fvg_top and first_fvg_bot:
                if curr.high >= first_fvg_bot and curr.low <= first_fvg_top and curr.close < curr.open:
                    entry_type = "⭐ A+ PRO SNIPER (First Presented FVG Retest)"

            # Type 3: C2 Upper Wick 50% Equilibrium Retest
            c2_wick_eq = (c2_high + max(c2_open, c2_close)) / 2.0
            if not entry_type and curr.high >= c2_wick_eq * 0.9995 and curr.close < curr.open:
                entry_type = "🎯 C2 WICK 50% EQ RETEST"

            # Type 1: Direct C3 Open Entry
            if not entry_type and len(c3_bars) <= 3 and curr.close < curr.open:
                entry_type = "⚡ DIRECT C3 OPEN ENTRY"

            if entry_type:
                sl = c2_high + (candle_range * 0.20)
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
                        reason=f"🔻 CRT [{htf_name.upper()} -> {timeframe.upper()}] Bearish C2 Sweep ({c1_high:.2f}) | {entry_type} + MANDATORY {div_info['type']}",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_info["type"],
                        is_ultra_strong=True
                    )

        return None
