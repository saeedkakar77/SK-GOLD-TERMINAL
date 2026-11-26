import uuid
import datetime
from typing import List, Optional, Tuple, Dict
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy
from core.volume_analyzer import VolumeDivergenceAnalyzer
from core.confirmation_analyzer import ConfirmationAnalyzer

class BreakerZone:
    def __init__(self, top: float, btm: float, is_bullish_breaker: bool, created_idx: int):
        self.top = top
        self.btm = btm
        # True = Bullish Breaker (Support), False = Bearish Breaker (Resistance)
        self.is_bullish_breaker = is_bullish_breaker
        self.created_idx = created_idx
        self.is_active = True

class IFvgZone:
    def __init__(self, top: float, btm: float, is_bullish_ifvg: bool, created_idx: int):
        self.top = top
        self.btm = btm
        self.mid = (top + btm) / 2.0
        # True = Bullish iFVG (Support), False = Bearish iFVG (Resistance)
        self.is_bullish_ifvg = is_bullish_ifvg
        self.created_idx = created_idx
        self.is_active = True

class BreakerIFVGUnicornStrategy(BaseStrategy):
    """
    Strategy 16: Breaker Block + Inversion FVG (iFVG) — The ICT Unicorn Setup
    Integrated with 2-Candle & 3-Candle Institutional Confirmation Candles + Mandatory Vol Div
    
    STRICT RULES:
    1. Timeframes: Strictly M15, M30, H1, H4, 1D, 1W, 1M only.
    2. Breaker Blocks (LuxAlgo Engine):
       - Broken Bearish OB flips into Bullish Breaker (Support).
       - Broken Bullish OB flips into Bearish Breaker (Resistance).
    3. Inversion FVG (iFVG Engine):
       - Broken Bearish FVG flips into Bullish iFVG (Support).
       - Broken Bullish FVG flips into Bearish iFVG (Resistance).
    4. Unicorn Confluence:
       - If Breaker Block and iFVG overlap in the same price range, tagged as 🦄 UNICORN A+ SETUP.
    5. Retest & Confirmation Candles (Mandatory):
       - Requires strict 2-Candle Confirmation (Engulfing / Rejection Sweep) OR 
         3-Candle Confirmation (Morning/Evening Star).
    6. Volume Divergence:
       - 100% MANDATORY (Regular or Hidden Vol Div aligned with setup).
    7. Fixed Risk-to-Reward:
       - TP 1 = 1:1.5 RR
       - TP 2 = 1:3.0 RR
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_breaker_ifvg_unicorn",
            name="Unicorn Setup: Breaker Block + iFVG + 2/3 Candle Conf + Vol Div",
            description="Breaker Block & Inversion FVG (M15-Monthly) with 2-Candle & 3-Candle Confirmation Candles + Mandatory Volume Divergence. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        # 1. Strict Timeframe Filter: M15, M30, H1, H4, 1D, 1W, 1M only
        tf_clean = timeframe.lower().strip()
        allowed_tfs = ["15m", "30m", "1h", "4h", "1d", "1w", "1m_month"]
        if tf_clean not in allowed_tfs:
            return None

        if len(candles) < 35:
            return None

        # 2. Strict MANDATORY Volume Divergence Check
        div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
        if not div_info:
            return None  # Vol Div is 100% MUST!

        div_type = div_info["type"].lower()
        is_div_bull = "bullish" in div_type
        is_div_bear = "bearish" in div_type

        # 3. Check Candlestick Confirmation Patterns (2-Candle or 3-Candle)
        bull_conf = ConfirmationAnalyzer.check_bullish_confirmation(candles) if is_div_bull else None
        bear_conf = ConfirmationAnalyzer.check_bearish_confirmation(candles) if is_div_bear else None

        if not bull_conf and not bear_conf:
            return None  # User Rule: Confirmation Candle is 100% MUST!

        curr = candles[-1]
        prev = candles[-2]
        digits = 2 if "XAU" in symbol.upper() else 5
        atr_series = self.calc_atr(candles, 14)
        curr_atr = atr_series[-1] if atr_series and atr_series[-1] > 0 else (curr.high - curr.low or 1.0)

        # 4. Scan Candle History for Breaker Blocks and iFVGs
        breakers: List[BreakerZone] = []
        ifvgs: List[IFvgZone] = []

        scan_start = max(2, len(candles) - 80)

        # A. Detect iFVGs across history
        for i in range(scan_start, len(candles) - 1):
            c_now = candles[i]
            c_prev1 = candles[i - 1]
            c_prev2 = candles[i - 2]

            # Bullish FVG formed at i
            if c_now.low > c_prev2.high and c_prev1.close > c_prev2.high:
                fvg_top = c_now.low
                fvg_btm = c_prev2.high
                # Check if price later closes below fvg_btm -> flips to Bearish iFVG
                for k in range(i + 1, len(candles) - 1):
                    if candles[k].close < fvg_btm:
                        ifvgs.append(IFvgZone(fvg_top, fvg_btm, is_bullish_ifvg=False, created_idx=k))
                        break

            # Bearish FVG formed at i
            elif c_now.high < c_prev2.low and c_prev1.close < c_prev2.low:
                fvg_top = c_prev2.low
                fvg_btm = c_now.high
                # Check if price later closes above fvg_top -> flips to Bullish iFVG
                for k in range(i + 1, len(candles) - 1):
                    if candles[k].close > fvg_top:
                        ifvgs.append(IFvgZone(fvg_top, fvg_btm, is_bullish_ifvg=True, created_idx=k))
                        break

        # B. Detect Breaker Blocks across history (Swing highs/lows lookback 5)
        for i in range(scan_start, len(candles) - 4):
            # Swing High
            if (candles[i].high > candles[i-1].high and candles[i].high > candles[i-2].high and
                candles[i].high > candles[i+1].high and candles[i].high > candles[i+2].high):
                sh_val = candles[i].high
                # Candidate Bullish OB at this swing
                ob_top = max(candles[i].open, candles[i].close)
                ob_btm = min(candles[i].open, candles[i].close)
                # Check if subsequent breakdown happens (close < ob_btm) -> Flips to Bearish Breaker
                for k in range(i + 3, len(candles) - 1):
                    if candles[k].close < ob_btm:
                        breakers.append(BreakerZone(ob_top, ob_btm, is_bullish_breaker=False, created_idx=k))
                        break

            # Swing Low
            if (candles[i].low < candles[i-1].low and candles[i].low < candles[i-2].low and
                candles[i].low < candles[i+1].low and candles[i].low < candles[i+2].low):
                sl_val = candles[i].low
                # Candidate Bearish OB at this swing
                ob_top = max(candles[i].open, candles[i].close)
                ob_btm = min(candles[i].open, candles[i].close)
                # Check if subsequent breakout happens (close > ob_top) -> Flips to Bullish Breaker
                for k in range(i + 3, len(candles) - 1):
                    if candles[k].close > ob_top:
                        breakers.append(BreakerZone(ob_top, ob_btm, is_bullish_breaker=True, created_idx=k))
                        break

        # Invalidate zones that were broken opposite side
        for b in breakers:
            if b.is_bullish_breaker and any(c.close < b.btm for c in candles[b.created_idx + 1:-1]):
                b.is_active = False
            elif not b.is_bullish_breaker and any(c.close > b.top for c in candles[b.created_idx + 1:-1]):
                b.is_active = False

        for f in ifvgs:
            if f.is_bullish_ifvg and any(c.close < f.btm for c in candles[f.created_idx + 1:-1]):
                f.is_active = False
            elif not f.is_bullish_ifvg and any(c.close > f.top for c in candles[f.created_idx + 1:-1]):
                f.is_active = False

        # =====================================================================
        # 5. EVALUATE BUY SETUP (Bullish Breaker OR Bullish iFVG Retest)
        # =====================================================================
        if bull_conf and is_div_bull:
            active_bull_brk = [b for b in breakers if b.is_active and b.is_bullish_breaker]
            active_bull_ifvg = [f for f in ifvgs if f.is_active and f.is_bullish_ifvg]

            tested_zone = None
            is_unicorn = False

            # Check for Unicorn (Overlap of Breaker and iFVG)
            for b in active_bull_brk:
                for f in active_bull_ifvg:
                    if max(b.btm, f.btm) <= min(b.top, f.top):
                        # Retest check of Unicorn support zone
                        u_top = max(b.top, f.top)
                        u_btm = min(b.btm, f.btm)
                        if (curr.low <= u_top and curr.high >= u_btm) or (prev.low <= u_top and prev.high >= u_btm):
                            tested_zone = (u_top, u_btm, "🦄 UNICORN (Bullish Breaker + Bullish iFVG Overlap)")
                            is_unicorn = True
                            break
                if is_unicorn:
                    break

            # If not unicorn, check single Bullish Breaker
            if not tested_zone:
                for b in active_bull_brk:
                    if (curr.low <= b.top and curr.high >= b.btm) or (prev.low <= b.top and prev.high >= b.btm):
                        tested_zone = (b.top, b.btm, "Bullish Breaker Block Support")
                        break

            # If not breaker, check single Bullish iFVG
            if not tested_zone:
                for f in active_bull_ifvg:
                    if (curr.low <= f.top and curr.high >= f.btm) or (prev.low <= f.top and prev.high >= f.btm):
                        tested_zone = (f.top, f.btm, "Bullish Inversion FVG (iFVG) Support")
                        break

            if tested_zone:
                z_top, z_btm, z_name = tested_zone
                entry_price = curr.close
                buffer = max(curr_atr * 0.25, 0.60 if "XAU" in symbol.upper() else 0.0009)
                stop_loss = round(min(z_btm, curr.low, prev.low) - buffer, digits)
                risk = entry_price - stop_loss
                if risk <= 0:
                    risk = max(curr_atr * 0.5, 1.20)
                    stop_loss = round(entry_price - risk, digits)

                tp1 = round(entry_price + (risk * 1.5), digits)
                tp2 = round(entry_price + (risk * 3.0), digits)

                setup_badge = "⭐ A+ UNICORN SETUP" if is_unicorn else "⭐ A+ BREAKOUT RETEST"
                return Signal(
                    id=str(uuid.uuid4())[:8],
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    timeframe=timeframe,
                    action="BUY",
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    reason=f"🔥 {setup_badge} [{timeframe.upper()}]: {z_name} Retest [{z_btm:.2f}-{z_top:.2f}] + {bull_conf['type']} + MANDATORY {div_info['type']}",
                    timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    vol_div=div_info["type"],
                    is_ultra_strong=True
                )

        # =====================================================================
        # 6. EVALUATE SELL SETUP (Bearish Breaker OR Bearish iFVG Retest)
        # =====================================================================
        if bear_conf and is_div_bear:
            active_bear_brk = [b for b in breakers if b.is_active and not b.is_bullish_breaker]
            active_bear_ifvg = [f for f in ifvgs if f.is_active and not f.is_bullish_ifvg]

            tested_zone = None
            is_unicorn = False

            # Check for Unicorn (Overlap of Bearish Breaker and Bearish iFVG)
            for b in active_bear_brk:
                for f in active_bear_ifvg:
                    if max(b.btm, f.btm) <= min(b.top, f.top):
                        # Retest check of Unicorn resistance zone
                        u_top = max(b.top, f.top)
                        u_btm = min(b.btm, f.btm)
                        if (curr.high >= u_btm and curr.low <= u_top) or (prev.high >= u_btm and prev.low <= u_top):
                            tested_zone = (u_top, u_btm, "🦄 UNICORN (Bearish Breaker + Bearish iFVG Overlap)")
                            is_unicorn = True
                            break
                if is_unicorn:
                    break

            # If not unicorn, check single Bearish Breaker
            if not tested_zone:
                for b in active_bear_brk:
                    if (curr.high >= b.btm and curr.low <= b.top) or (prev.high >= b.btm and prev.low <= b.top):
                        tested_zone = (b.top, b.btm, "Bearish Breaker Block Resistance")
                        break

            # If not breaker, check single Bearish iFVG
            if not tested_zone:
                for f in active_bear_ifvg:
                    if (curr.high >= f.btm and curr.low <= f.top) or (prev.high >= f.btm and prev.low <= f.top):
                        tested_zone = (f.top, f.btm, "Bearish Inversion FVG (iFVG) Resistance")
                        break

            if tested_zone:
                z_top, z_btm, z_name = tested_zone
                entry_price = curr.close
                buffer = max(curr_atr * 0.25, 0.60 if "XAU" in symbol.upper() else 0.0009)
                stop_loss = round(max(z_top, curr.high, prev.high) + buffer, digits)
                risk = stop_loss - entry_price
                if risk <= 0:
                    risk = max(curr_atr * 0.5, 1.20)
                    stop_loss = round(entry_price + risk, digits)

                tp1 = round(entry_price - (risk * 1.5), digits)
                tp2 = round(entry_price - (risk * 3.0), digits)

                setup_badge = "⭐ A+ UNICORN SETUP" if is_unicorn else "⭐ A+ BREAKOUT RETEST"
                return Signal(
                    id=str(uuid.uuid4())[:8],
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    timeframe=timeframe,
                    action="SELL",
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    reason=f"🔥 {setup_badge} [{timeframe.upper()}]: {z_name} Retest [{z_btm:.2f}-{z_top:.2f}] + {bear_conf['type']} + MANDATORY {div_info['type']}",
                    timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    vol_div=div_info["type"],
                    is_ultra_strong=True
                )

        return None
