import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class MSNRStrategy(BaseStrategy):
    """
    Strategy 10: MSNR Price Action (CL A/V Shapes, OCL, SBR & RBS Flips)
    STRICT TIMEFRAME RESTRICTION:
    - Only valid on: M30, H1, H4, Daily (1D), Weekly (1W), Monthly (1M).
    - Blocked on anything below M30 (M1, M3, M5, M15).
    - Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_msnr_snr",
            name="MSNR: CL, OCL, SBR & RBS (M30 - Monthly)",
            description="Modern SNR with SBR/RBS Flips. Strictly active on M30, H1, H4, 1D, 1W, 1M only. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        tf = timeframe.lower().strip()
        # Strictly restricted to M30, H1, H4, Daily, Weekly, Monthly
        allowed_tfs = ["30m", "1h", "4h", "1d", "1w", "1m_month", "daily", "weekly", "monthly", "d", "w", "m"]
        if tf not in allowed_tfs:
            return None

        if len(candles) < 30:
            return None

        curr = candles[-1]
        prev = candles[-2]

        # Scan for historical CL (A Peaks and V Valleys) and track SBR/RBS Flips
        rbs_levels = []  # Resistance broken up -> Becomes Support (BUY)
        sbr_levels = []  # Support broken down -> Becomes Resistance (SELL)
        fresh_supports = []
        fresh_resistances = []

        for i in range(len(candles) - 30, len(candles) - 2):
            if i < 2:
                continue

            # 1. 'A' Peak: Green -> Red (Resistance)
            is_green_prev = candles[i-1].close > candles[i-1].open
            is_red_curr   = candles[i].close < candles[i].open
            if is_green_prev and is_red_curr:
                peak_price = max(candles[i-1].close, candles[i].open)
                # Check if broken by subsequent candle body -> RBS
                broken_up = any(candles[j].close > peak_price for j in range(i+1, len(candles)-1))
                if broken_up:
                    rbs_levels.append(peak_price)
                else:
                    fresh_resistances.append(peak_price)

            # 2. 'V' Valley: Red -> Green (Support)
            is_red_prev    = candles[i-1].close < candles[i-1].open
            is_green_curr  = candles[i].close > candles[i].open
            if is_red_prev and is_green_curr:
                valley_price = min(candles[i-1].close, candles[i].open)
                # Check if broken by subsequent candle body -> SBR
                broken_down = any(candles[j].close < valley_price for j in range(i+1, len(candles)-1))
                if broken_down:
                    sbr_levels.append(valley_price)
                else:
                    fresh_supports.append(valley_price)

        candle_range = max(curr.high - curr.low, 0.0001)
        lower_wick = min(curr.open, curr.close) - curr.low
        upper_wick = curr.high - max(curr.open, curr.close)

        # 🟢 BUY EVALUATION (RBS or Fresh V-Support Retest):
        support_targets = rbs_levels[-3:] + fresh_supports[-2:]
        for sup in support_targets:
            # Retest condition: price dips and touches support level
            tested = (curr.low <= sup * 1.0008 and curr.high >= sup * 0.9992) or (prev.low <= sup and prev.high >= sup)
            body_held = curr.close >= sup and curr.open >= sup
            is_rejection = (curr.close > curr.open) and ((lower_wick / candle_range) >= 0.30 or curr.close > prev.high)

            if tested and body_held and is_rejection:
                sl = sup - (candle_range * 0.30)
                risk = curr.close - sl
                if risk > 0:
                    tp1 = round(curr.close + (risk * 1.5), 2 if "XAU" in symbol else 5)
                    tp2 = round(curr.close + (risk * 3.0), 2 if "XAU" in symbol else 5)
                    lvl_name = "RBS Flip Support" if sup in rbs_levels else "Fresh 'V' Support"
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
                        reason=f"💎 MSNR {lvl_name} ({sup:.2f}) Retest & Bullish Rejection on {timeframe.upper()} [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        # 🔴 SELL EVALUATION (SBR or Fresh A-Resistance Retest):
        resistance_targets = sbr_levels[-3:] + fresh_resistances[-2:]
        for res in resistance_targets:
            tested = (curr.high >= res * 0.9992 and curr.low <= res * 1.0008) or (prev.high >= res and prev.low <= res)
            body_held = curr.close <= res and curr.open <= res
            is_rejection = (curr.close < curr.open) and ((upper_wick / candle_range) >= 0.30 or curr.close < prev.low)

            if tested and body_held and is_rejection:
                sl = res + (candle_range * 0.30)
                risk = sl - curr.close
                if risk > 0:
                    tp1 = round(curr.close - (risk * 1.5), 2 if "XAU" in symbol else 5)
                    tp2 = round(curr.close - (risk * 3.0), 2 if "XAU" in symbol else 5)
                    lvl_name = "SBR Flip Resistance" if res in sbr_levels else "Fresh 'A' Resistance"
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
                        reason=f"🔻 MSNR {lvl_name} ({res:.2f}) Retest & Bearish Rejection on {timeframe.upper()} [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        return None
