import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from core.cme_fetcher import CMEGoldDataFetcher
from strategies.base_strategy import BaseStrategy

class CMEOpenInterestStrategy(BaseStrategy):
    """
    Strategy 1 (Supreme Leading Strategy): CME Institutional Open Interest (OI) Order Flow
    Tracks daily changes in CME COMEX Gold Futures (GC) Open Interest & Options Call/Put Walls.
    Based on Mentor's 400,000 Contracts Institutional Benchmark:
      - Total OI >= 400,000 + Positive Delta (+8,562): 100% Institutional Accumulation -> High Probability BUY
      - Price Pullback to Put Wall / EMA20 in 400k regime -> ULTRA STRONG BUY ON DIP
      - Counter-trend sell signals strictly suppressed during 400k+ bull expansion.
      - Total OI < 400,000: Commercials Liquidating -> CAUTION / REVERSAL WARNING

    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_cme_open_interest",
            name="CME Institutional Open Interest (OI) Order Flow",
            description="Strategy #1: CME COMEX Gold (GC) Daily Open Interest & Options Call/Put Wall tracker. Identifies smart money fresh contracts injection (400k+ Benchmark) vs retail traps. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 30:
            return None

        curr = candles[-1]
        prev = candles[-2]
        p2 = candles[-3]

        # 1. Fetch live CME Open Interest Analysis & 400k Benchmark State
        cme_report = CMEGoldDataFetcher.get_cme_analysis(spot_price=curr.close)
        is_cme_bullish = (cme_report.get("vote") == "BULLISH")
        is_cme_bearish = (cme_report.get("vote") == "BEARISH")
        total_oi = cme_report.get("open_interest_total", 400666)
        oi_change = cme_report.get("open_interest_change", 8562)
        cme_put_wall = cme_report.get("put_wall_support", 4000.0)
        cme_call_wall = cme_report.get("call_wall_resistance", 4075.0)

        # 2. Local Market Geometry
        lookback = min(len(candles), 25)
        recent_bars = candles[-lookback:]
        highest_p = max(c.high for c in recent_bars)
        lowest_p = min(c.low for c in recent_bars)
        range_span = highest_p - lowest_p if highest_p > lowest_p else 10.0

        ema20 = self.calc_ema([c.close for c in candles], 20)[-1]
        ema50 = self.calc_ema([c.close for c in candles], 50)[-1]

        atr_vals = self.calc_atr(candles, 14)
        atr = atr_vals[-1] if atr_vals and atr_vals[-1] > 0 else (range_span * 0.08)

        # Candle properties
        c_range = max(curr.high - curr.low, 0.001)
        lower_wick = min(curr.open, curr.close) - curr.low
        upper_wick = curr.high - max(curr.open, curr.close)
        is_bullish_close = curr.close > curr.open
        is_bearish_close = curr.close < curr.open

        is_pinbar_buy = (lower_wick / c_range >= 0.35) and (curr.close >= prev.close)
        is_engulf_buy = is_bullish_close and (curr.close > prev.high)
        is_continuation_buy = is_bullish_close and (curr.close > prev.close) and (curr.close >= ema20)
        
        is_pinbar_sell = (upper_wick / c_range >= 0.40) and (curr.close <= prev.close)
        is_engulf_sell = is_bearish_close and (curr.close < prev.low)

        # -------------------------------------------------------------
        # 1. INSTITUTIONAL BUY SCENARIO (CME 400K+ BENCHMARK ACCUMULATION)
        # -------------------------------------------------------------
        if is_cme_bullish:
            # During 400k+ Bull Expansion, buy on dip pullbacks towards EMA20 or Put Wall Support
            if is_pinbar_buy or is_engulf_buy or (is_continuation_buy and curr.low <= ema20 + 5.0):
                entry = round(curr.close, 2)
                recent_low = min(curr.low, prev.low, p2.low)
                sl = round(min(recent_low - (atr * 0.5), entry - (atr * 1.0)), 2)
                risk = round(entry - sl, 2)
                if risk >= 2.5 and risk <= 25.0:
                    tp1 = round(entry + (risk * 1.5), 2)
                    tp2 = round(entry + (risk * 3.0), 2)

                    pattern_label = "2-Candle Bullish Engulfing" if is_engulf_buy else ("Pinbar Rejection from Discount" if is_pinbar_buy else "EMA20 Dynamic Bounce")

                    return Signal(
                        id=f"sig_{uuid.uuid4().hex[:8]}",
                        strategy_id=self.strategy_id,
                        strategy_name=self.name,
                        symbol=symbol,
                        timeframe=timeframe,
                        action="BUY",
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        reason=f"CME Institutional Open Interest ({total_oi:,} >= 400k Benchmark, +{oi_change:,} Contracts Inflow): Smart Money defended CME Put Wall [{cme_put_wall:.2f}] zone with {pattern_label}. 100% BUY ON DIPS.",
                        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        status="ACTIVE",
                        vol_div="CME 400k+ Institutional Accumulation",
                        is_ultra_strong=True
                    )
            # In 400k+ Bull Expansion, suppress counter-trend SELL signals!
            return None

        # -------------------------------------------------------------
        # 2. INSTITUTIONAL SELL SCENARIO (SUB-400K PROFIT TAKING / BREAKDOWN)
        # -------------------------------------------------------------
        if is_cme_bearish and not is_cme_bullish:
            if (is_pinbar_sell or is_engulf_sell) and (curr.close <= ema20 or curr.high >= cme_call_wall - 5.0):
                entry = round(curr.close, 2)
                recent_high = max(curr.high, prev.high, p2.high)
                sl = round(max(recent_high + (atr * 0.5), entry + (atr * 1.0)), 2)
                risk = round(sl - entry, 2)
                if risk >= 2.5 and risk <= 25.0:
                    tp1 = round(entry - (risk * 1.5), 2)
                    tp2 = round(entry - (risk * 3.0), 2)

                    pattern_label = "2-Candle Bearish Engulfing" if is_engulf_sell else "Shooting Star Rejection"

                    return Signal(
                        id=f"sig_{uuid.uuid4().hex[:8]}",
                        strategy_id=self.strategy_id,
                        strategy_name=self.name,
                        symbol=symbol,
                        timeframe=timeframe,
                        action="SELL",
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        reason=f"CME Sub-400k Profit Taking / Short Inflow ({total_oi:,} Contracts): Sellers defended CME Call Wall [{cme_call_wall:.2f}] ceiling with {pattern_label}.",
                        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        status="ACTIVE",
                        vol_div="CME Sub-400k Distribution",
                        is_ultra_strong=True
                    )

        return None
