import uuid
import datetime
import math
from typing import List, Optional, Tuple, Dict
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy
from core.volume_analyzer import VolumeDivergenceAnalyzer

class BBMAMultiTFStrategy(BaseStrategy):
    """
    Strategy 15: BBMA Oma Ally (Multiple Timeframe Triad System) + Mandatory Volume Divergence
    
    EXACT RULES (From 18 Institutional Diagrams & Screenshot 13 Table):
    1. Multi-Timeframe Triads (TF1 -> TF2 -> TF3):
       - Monthly (1M)  -> Weekly (1W)  -> Execution Signal on Daily (1D)
       - Daily (1D)    -> H4 (4H)      -> Execution Signal on H1 (1H)
       - H4 (4H)       -> H1 (1H)      -> Execution Signal on M15 (15M)
       - H1 (1H)       -> M15 (15M)    -> Execution Signal on M5 (5M)
       
    2. The 4 Master BBMA Codes:
       - Code 1: R - E - M  (Re-entry on TF1, Extreme on TF2, MHV + Rejection on TF3)
       - Code 2: R - R - E  (Re-entry on TF1, Re-entry on TF2, Extreme + Reversal on TF3)
       - Code 3: R - E - E  (Re-entry on TF1, Advance Extreme on TF2, Extreme + CSAK on TF3)
       - Code 4: R - M - EE (Re-entry on TF1, MHV on TF2, Double Extreme on TF3)
       
    3. Mandatory Volume Divergence:
       - Aligned Volume Divergence (Regular or Hidden) MUST be present on TF3 execution.
       
    4. Fixed Risk-to-Reward:
       - TP 1 = 1:1.5 RR
       - TP 2 = 1:3.0 RR
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_bbma_multi_tf",
            name="BBMA Multi-TF: Triads (REE, REM, RRE) + Vol Div",
            description="BBMA Oma Ally Multiple Timeframe Engine (H1->M5, H4->M15, 1D->H1, 1M->1D) with 4 Codes (REM, RRE, REE, RMEE) + Mandatory Vol Div. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def _get_triad_mapping(self, ltf: str) -> Optional[Tuple[str, str, int, int]]:
        """
        Returns (TF1_name, TF2_name, step_tf2, step_tf1)
        where step is the number of LTF (TF3) bars per parent candle.
        """
        ltf_clean = ltf.lower().strip()
        mapping = {
            "5m":  ("1h",  "15m", 3, 12),     # 3 bars of 5m = 15m; 12 bars of 5m = 1h
            "15m": ("4h",  "1h",  4, 16),     # 4 bars of 15m = 1h; 16 bars of 15m = 4h
            "1h":  ("1d",  "4h",  4, 24),     # 4 bars of 1h = 4h; 24 bars of 1h = 1d
            "1d":  ("1m_month", "1w", 5, 22)  # 5 days = 1w; 22 days = 1 month
        }
        return mapping.get(ltf_clean)

    @staticmethod
    def _calc_bb(closes: List[float], period: int = 20, mult: float = 2.0) -> Tuple[float, float, float]:
        """Calculates current Upper, Basis (Mid), Lower Bollinger Bands."""
        if len(closes) < period:
            c = closes[-1] if closes else 0.0
            return c, c, c
        slice_vals = closes[-period:]
        basis = sum(slice_vals) / period
        variance = sum((x - basis) ** 2 for x in slice_vals) / period
        stdev = math.sqrt(variance)
        upper = basis + (mult * stdev)
        lower = basis - (mult * stdev)
        return upper, basis, lower

    def _aggregate_htf(self, candles: List[Candle], step: int) -> List[Candle]:
        """Resamples LTF candles into synthetic HTF candles."""
        htf_candles = []
        n = len(candles)
        for i in range(0, n - (n % step), step):
            chunk = candles[i:i + step]
            if not chunk:
                continue
            o = chunk[0].open
            h = max(c.high for c in chunk)
            l = min(c.low for c in chunk)
            c = chunk[-1].close
            v = sum(c.volume for c in chunk)
            t = chunk[0].time
            htf_candles.append(Candle(time=t, open=o, high=h, low=l, close=c, volume=v))
        return htf_candles

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        triad = self._get_triad_mapping(timeframe)
        if not triad:
            return None  # Only evaluate on designated TF3 execution timeframes (5m, 15m, 1h, 1d)

        tf1_name, tf2_name, step_tf2, step_tf1 = triad

        # Ensure enough historical data to construct at least 25 bars of TF1
        min_bars_needed = step_tf1 * 25
        if len(candles) < min_bars_needed:
            return None

        # 1. MANDATORY Volume Divergence Check
        div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
        if not div_info:
            return None  # Rule: Vol Div is 100% MUST!

        div_type = div_info["type"].lower()
        is_div_bull = "bullish" in div_type
        is_div_bear = "bearish" in div_type

        # 2. Build Multi-Timeframe Series
        tf3_candles = candles
        tf2_candles = self._aggregate_htf(candles, step_tf2)
        tf1_candles = self._aggregate_htf(candles, step_tf1)

        if len(tf1_candles) < 20 or len(tf2_candles) < 20 or len(tf3_candles) < 25:
            return None

        # Current bars on all 3 timeframes
        c_tf1 = tf1_candles[-1]
        c_tf2 = tf2_candles[-1]
        c_tf3 = tf3_candles[-1]
        prev_tf3 = tf3_candles[-2]

        # Calculate indicators for TF1
        tf1_closes = [c.close for c in tf1_candles]
        tf1_up, tf1_mid, tf1_low = self._calc_bb(tf1_closes, 20)
        tf1_ma5_h = sum(c.high for c in tf1_candles[-5:]) / 5.0
        tf1_ma10_h = sum(c.high for c in tf1_candles[-10:]) / 10.0
        tf1_ma5_l = sum(c.low for c in tf1_candles[-5:]) / 5.0
        tf1_ma10_l = sum(c.low for c in tf1_candles[-10:]) / 10.0
        tf1_ema50 = self.calc_ema(tf1_closes, 50)[-1] if len(tf1_closes) >= 50 else tf1_mid

        # Calculate indicators for TF2
        tf2_closes = [c.close for c in tf2_candles]
        tf2_up, tf2_mid, tf2_low = self._calc_bb(tf2_closes, 20)
        tf2_ma5_h = sum(c.high for c in tf2_candles[-5:]) / 5.0
        tf2_ma10_h = sum(c.high for c in tf2_candles[-10:]) / 10.0
        tf2_ma5_l = sum(c.low for c in tf2_candles[-5:]) / 5.0
        tf2_ma10_l = sum(c.low for c in tf2_candles[-10:]) / 10.0
        tf2_ema50 = self.calc_ema(tf2_closes, 50)[-1] if len(tf2_closes) >= 50 else tf2_mid

        # Calculate indicators for TF3
        tf3_closes = [c.close for c in tf3_candles]
        tf3_up, tf3_mid, tf3_low = self._calc_bb(tf3_closes, 20)
        tf3_ma5_h = sum(c.high for c in tf3_candles[-5:]) / 5.0
        tf3_ma10_h = sum(c.high for c in tf3_candles[-10:]) / 10.0
        tf3_ma5_l = sum(c.low for c in tf3_candles[-5:]) / 5.0
        tf3_ma10_l = sum(c.low for c in tf3_candles[-10:]) / 10.0

        digits = 2 if "XAU" in symbol.upper() else 5

        # =====================================================================
        # 3. EVALUATE BULLISH BBMA CODES (BUY SETUPS)
        # =====================================================================
        if is_div_bull:
            # TF1 Check: Re-entry Buy (R)
            # Price pulls back into MA5/10 Low ribbon while above EMA50 or Mid BB
            tf1_reentry_buy = (c_tf1.low <= max(tf1_ma5_l, tf1_ma10_l) and c_tf1.close >= min(tf1_ma5_l, tf1_ma10_l)) or \
                              (c_tf1.close > tf1_ema50 and c_tf1.low <= tf1_ma5_l * 1.002)

            if tf1_reentry_buy:
                # TF2 Checks: Extreme (E) or Re-entry (R) or MHV (M)
                tf2_extreme_buy = (c_tf2.low <= tf2_low or tf2_ma5_l <= tf2_low) or (abs(c_tf2.low - tf2_ema50) / tf2_ema50 < 0.003)
                tf2_reentry_buy = c_tf2.low <= max(tf2_ma5_l, tf2_ma10_l)
                tf2_mhv_buy = (c_tf2.low <= tf2_low * 1.003 and c_tf2.close > tf2_low)

                # TF3 Checks: Extreme (E), MHV (M), or CSAK Buy Breakout
                tf3_extreme_buy = (c_tf3.low <= tf3_low or tf3_ma5_l <= tf3_low)
                tf3_mhv_buy = (c_tf3.low <= tf3_low * 1.002 and c_tf3.close > tf3_low)
                tf3_csak_buy = (c_tf3.close > tf3_mid and c_tf3.close > max(tf3_ma5_h, tf3_ma10_h))
                tf3_bounce_conf = (c_tf3.close > c_tf3.open and (c_tf3.close > prev_tf3.close or c_tf3.high > prev_tf3.high))

                detected_code = None
                if tf2_extreme_buy and (tf3_mhv_buy or tf3_csak_buy or tf3_bounce_conf):
                    detected_code = "R-E-M" if tf3_mhv_buy else "R-E-E (Advance Extreme + CSAK)"
                elif tf2_reentry_buy and (tf3_extreme_buy or tf3_csak_buy):
                    detected_code = "R-R-E"
                elif tf2_mhv_buy and tf3_extreme_buy:
                    detected_code = "R-M-EE"

                if detected_code:
                    entry_price = c_tf3.close
                    # SL placed below the recent swing low / Lower BB with safe buffer
                    buffer = max((c_tf3.high - c_tf3.low) * 0.4, 0.60 if "XAU" in symbol.upper() else 0.0009)
                    stop_loss = round(min(c_tf3.low, prev_tf3.low, tf3_low) - buffer, digits)
                    risk = entry_price - stop_loss
                    if risk <= 0:
                        risk = 1.50 if "XAU" in symbol.upper() else 0.0015
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
                        reason=f"🔥 BBMA [{tf1_name.upper()}->{tf2_name.upper()}->{timeframe.upper()}]: Code {detected_code} BUY Setup | TF1 Re-entry + TF2/TF3 Confirmation + MANDATORY {div_info['type']}",
                        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_info["type"],
                        is_ultra_strong=True
                    )

        # =====================================================================
        # 4. EVALUATE BEARISH BBMA CODES (SELL SETUPS)
        # =====================================================================
        if is_div_bear:
            # TF1 Check: Re-entry Sell (R)
            # Price rallies into MA5/10 High ribbon while below EMA50 or Mid BB
            tf1_reentry_sell = (c_tf1.high >= min(tf1_ma5_h, tf1_ma10_h) and c_tf1.close <= max(tf1_ma5_h, tf1_ma10_h)) or \
                               (c_tf1.close < tf1_ema50 and c_tf1.high >= tf1_ma5_h * 0.998)

            if tf1_reentry_sell:
                # TF2 Checks: Extreme (E) or Re-entry (R) or MHV (M)
                tf2_extreme_sell = (c_tf2.high >= tf2_up or tf2_ma5_h >= tf2_up) or (abs(c_tf2.high - tf2_ema50) / tf2_ema50 < 0.003)
                tf2_reentry_sell = c_tf2.high >= min(tf2_ma5_h, tf2_ma10_h)
                tf2_mhv_sell = (c_tf2.high >= tf2_up * 0.997 and c_tf2.close < tf2_up)

                # TF3 Checks: Extreme (E), MHV (M), or CSAK Sell Breakdown
                tf3_extreme_sell = (c_tf3.high >= tf3_up or tf3_ma5_h >= tf3_up)
                tf3_mhv_sell = (c_tf3.high >= tf3_up * 0.998 and c_tf3.close < tf3_up)
                tf3_csak_sell = (c_tf3.close < tf3_mid and c_tf3.close < min(tf3_ma5_l, tf3_ma10_l))
                tf3_reject_conf = (c_tf3.close < c_tf3.open and (c_tf3.close < prev_tf3.close or c_tf3.low < prev_tf3.low))

                detected_code = None
                if tf2_extreme_sell and (tf3_mhv_sell or tf3_csak_sell or tf3_reject_conf):
                    detected_code = "R-E-M" if tf3_mhv_sell else "R-E-E (Advance Extreme + CSAK)"
                elif tf2_reentry_sell and (tf3_extreme_sell or tf3_csak_sell):
                    detected_code = "R-R-E"
                elif tf2_mhv_sell and tf3_extreme_sell:
                    detected_code = "R-M-EE"

                if detected_code:
                    entry_price = c_tf3.close
                    # SL placed above the recent swing high / Upper BB with safe buffer
                    buffer = max((c_tf3.high - c_tf3.low) * 0.4, 0.60 if "XAU" in symbol.upper() else 0.0009)
                    stop_loss = round(max(c_tf3.high, prev_tf3.high, tf3_up) + buffer, digits)
                    risk = stop_loss - entry_price
                    if risk <= 0:
                        risk = 1.50 if "XAU" in symbol.upper() else 0.0015
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
                        reason=f"🔥 BBMA [{tf1_name.upper()}->{tf2_name.upper()}->{timeframe.upper()}]: Code {detected_code} SELL Setup | TF1 Re-entry + TF2/TF3 Confirmation + MANDATORY {div_info['type']}",
                        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        vol_div=div_info["type"],
                        is_ultra_strong=True
                    )

        return None
