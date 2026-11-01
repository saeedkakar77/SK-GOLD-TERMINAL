import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy
from core.volume_analyzer import VolumeDivergenceAnalyzer

class EFZone:
    def __init__(self, top: float, bottom: float, start_idx: int, is_bull: bool):
        self.top = top
        self.bottom = bottom
        self.start_idx = start_idx
        self.is_bull = is_bull      # Original EG direction: True = Bullish EG, False = Bearish EG
        self.is_failed = False     # True once the EG is broken and flips to EF
        self.is_active = True      # Becomes False if invalidated after flip
        self.was_entered = False

class FailedEngulfingStrategy(BaseStrategy):
    """
    Strategy 14: EF BY SK (Failed Engulfing Engine) + Retest Confirmation + MANDATORY Volume Divergence
    
    STRICT USER RULES:
    1. Timeframes: Strictly M5, M15, M30, H1, H4 only.
    2. Detection:
       - Detects strong Engulfing candles (Body >= 0.8 * ATR14 and Body > Prev Body).
       - Original Engulfing zones remain invisible/pending until they FAIL.
       - Bullish EG fails when price closes BELOW the zone bottom -> Flips to Bearish EF Resistance.
       - Bearish EG fails when price closes ABOVE the zone top -> Flips to Bullish EF Support.
    3. Retest & Confirmation:
       - Price retests the EF zone.
       - A strong confirmation rejection candle (Pinbar/Hammer/Shooting Star or Engulfing) forms.
    4. MANDATORY Volume Divergence:
       - Setup MUST be confirmed by aligned Volume Divergence (Regular or Hidden).
    5. Fixed Risk-to-Reward:
       - TP 1 = 1:1.5 RR
       - TP 2 = 1:3.0 RR
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_ef_engulfing_fail",
            name="EF Setup: Failed Engulfing Retest + Vol Div",
            description="Failed Engulfing (EF) Zone Retest + Confirmation Rejection Candle + MANDATORY Volume Divergence (Strictly M5, M15, M30, H1, H4). [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        # 1. Strict Timeframe Filter: M5, M15, M30, H1, H4 only
        tf_clean = timeframe.lower().strip()
        allowed_tfs = ["5m", "15m", "30m", "1h", "4h"]
        if tf_clean not in allowed_tfs:
            return None

        if len(candles) < 35:
            return None

        # 2. Strict MANDATORY Volume Divergence Check
        div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
        if not div_info:
            return None  # User Rule: Volume Divergence is 100% MUST!

        div_type = div_info["type"].lower()
        is_div_bull = "bullish" in div_type
        is_div_bear = "bearish" in div_type

        # 3. Calculate ATR for significance filtering
        atr_series = self.calc_atr(candles, 14)
        curr = candles[-1]
        prev = candles[-2]
        curr_atr = atr_series[-1] if atr_series and atr_series[-1] > 0 else (curr.high - curr.low or 1.0)
        digits = 2 if "XAU" in symbol.upper() else 5

        # 4. Scan candle history to detect Engulfing zones and track Failures (EF Flips)
        zones: List[EFZone] = []
        scan_start = max(1, len(candles) - 100)

        for i in range(scan_start, len(candles) - 1):
            c_prev = candles[i - 1]
            c_curr = candles[i]
            body_curr = abs(c_curr.close - c_curr.open)
            body_prev = abs(c_prev.close - c_prev.open)
            atr_i = atr_series[i] if i < len(atr_series) and atr_series[i] > 0 else curr_atr

            is_big_enough = body_curr >= (atr_i * 0.8) and (body_curr > body_prev)

            # Bullish Engulfing Detection
            is_bull_eg = (c_curr.close > c_curr.open and 
                          c_prev.close < c_prev.open and 
                          c_curr.close >= c_prev.open and 
                          c_curr.open <= c_prev.close and 
                          is_big_enough)

            # Bearish Engulfing Detection
            is_bear_eg = (c_curr.close < c_curr.open and 
                          c_prev.close > c_prev.open and 
                          c_curr.close <= c_prev.open and 
                          c_curr.open >= c_prev.close and 
                          is_big_enough)

            if is_bull_eg:
                top = max(c_prev.open, c_prev.close)
                bot = min(c_prev.open, c_prev.close)
                zones.append(EFZone(top, bot, i, is_bull=True))
            elif is_bear_eg:
                top = max(c_prev.open, c_prev.close)
                bot = min(c_prev.open, c_prev.close)
                zones.append(EFZone(top, bot, i, is_bull=False))

            # Update lifecycle of active zones
            for z in zones:
                if not z.is_active:
                    continue

                if not z.is_failed:
                    # Check if original EG fails
                    if i > z.start_idx + 1:
                        if z.is_bull and c_curr.close < z.bottom:
                            # Bullish EG FAILED -> Flips to Bearish EF Resistance
                            z.is_failed = True
                            z.is_bull = False
                        elif not z.is_bull and c_curr.close > z.top:
                            # Bearish EG FAILED -> Flips to Bullish EF Support
                            z.is_failed = True
                            z.is_bull = True
                else:
                    # Already failed zone: check for second-side invalidation
                    if z.is_bull and c_curr.close < z.bottom:
                        z.is_active = False
                    elif not z.is_bull and c_curr.close > z.top:
                        z.is_active = False

        # 5. Check if current/recent candle is retesting an active Failed Engulfing (EF) zone
        # with confirmation rejection candle
        for z in reversed(zones):
            if not z.is_active or not z.is_failed:
                continue

            # Must have failed at least 1 bar before current entry
            if z.start_idx >= len(candles) - 2:
                continue

            # -----------------------------------------------------------------
            # CASE A: BUY SETUP (Bearish EG Failed -> Flips to Bullish EF Support)
            # -----------------------------------------------------------------
            if z.is_bull and is_div_bull:
                # Retest check: Price must have dipped into or touched the EF Support zone
                tested = (curr.low <= z.top and curr.high >= z.bottom) or (prev.low <= z.top and prev.high >= z.bottom)
                if not tested:
                    continue

                # Confirmation Candle Check:
                # 1. Lower rejection wick >= 30% of total candle range OR
                # 2. Bullish Close holding above the zone bottom OR
                # 3. Bullish engulfing / hammer
                total_range = curr.high - curr.low
                if total_range <= 0:
                    continue

                lower_wick = min(curr.open, curr.close) - curr.low
                wick_rejection = (lower_wick / total_range) >= 0.30
                bullish_close = curr.close > curr.open and curr.close >= z.bottom
                bounce_action = (curr.close > prev.close or curr.close > prev.high) and curr.close >= z.bottom

                if (wick_rejection or bullish_close or bounce_action) and curr.close >= z.bottom:
                    # Confirmed BUY Entry!
                    entry_price = curr.close
                    # SL placed strictly below EF zone bottom or lowest rejection wick with buffer
                    buffer = max(curr_atr * 0.20, 0.50 if "XAU" in symbol.upper() else 0.0008)
                    stop_loss = round(min(z.bottom, curr.low, prev.low) - buffer, digits)
                    risk = entry_price - stop_loss
                    if risk <= 0:
                        risk = max(curr_atr * 0.5, 1.0)
                        stop_loss = round(entry_price - risk, digits)

                    tp1 = round(entry_price + (risk * 1.5), digits)
                    tp2 = round(entry_price + (risk * 3.0), digits)

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
                        reason=f"🔥 EF SETUP [{timeframe.upper()}]: Bearish Engulfing Failed & Flipped to Support | Zone Retest [{z.bottom:.2f}-{z.top:.2f}] + Bullish Rejection Confirmation + MANDATORY {div_info['type']}",
                        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_info["type"],
                        is_ultra_strong=True
                    )

            # -----------------------------------------------------------------
            # CASE B: SELL SETUP (Bullish EG Failed -> Flips to Bearish EF Resistance)
            # -----------------------------------------------------------------
            elif (not z.is_bull) and is_div_bear:
                # Retest check: Price must have rallied into or touched the EF Resistance zone
                tested = (curr.high >= z.bottom and curr.low <= z.top) or (prev.high >= z.bottom and prev.low <= z.top)
                if not tested:
                    continue

                # Confirmation Candle Check:
                # 1. Upper rejection wick >= 30% of total candle range OR
                # 2. Bearish Close holding below the zone top OR
                # 3. Bearish engulfing / shooting star
                total_range = curr.high - curr.low
                if total_range <= 0:
                    continue

                upper_wick = curr.high - max(curr.open, curr.close)
                wick_rejection = (upper_wick / total_range) >= 0.30
                bearish_close = curr.close < curr.open and curr.close <= z.top
                reject_action = (curr.close < prev.close or curr.close < prev.low) and curr.close <= z.top

                if (wick_rejection or bearish_close or reject_action) and curr.close <= z.top:
                    # Confirmed SELL Entry!
                    entry_price = curr.close
                    # SL placed strictly above EF zone top or highest rejection wick with buffer
                    buffer = max(curr_atr * 0.20, 0.50 if "XAU" in symbol.upper() else 0.0008)
                    stop_loss = round(max(z.top, curr.high, prev.high) + buffer, digits)
                    risk = stop_loss - entry_price
                    if risk <= 0:
                        risk = max(curr_atr * 0.5, 1.0)
                        stop_loss = round(entry_price + risk, digits)

                    tp1 = round(entry_price - (risk * 1.5), digits)
                    tp2 = round(entry_price - (risk * 3.0), digits)

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
                        reason=f"🔥 EF SETUP [{timeframe.upper()}]: Bullish Engulfing Failed & Flipped to Resistance | Zone Retest [{z.bottom:.2f}-{z.top:.2f}] + Bearish Rejection Confirmation + MANDATORY {div_info['type']}",
                        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_info["type"],
                        is_ultra_strong=True
                    )

        return None
