import math
import datetime
from typing import List, Dict, Optional, Tuple
from core.models import Candle
from core.data_feed import DataFeedManager

class ICTBiasEngine:
    """
    MASTER ENGINE — ICT INSTITUTIONAL ERL/IRL MTF BIAS ANALYZER (V2.2)
    Universal Market Analysis across:
    1. MONTHLY (Macro Bias & PMH/PML Dealing Range)
    2. WEEKLY (Institutional Intermediate Bias & PWH/PWL)
    3. DAILY (Liquidity Objective & PDH/PDL Delivery)
    4. H4 (Directional Confirmation & MSS)
    
    Determines overall MTF Bias, Draw On Liquidity (DOL), and 2 Trade Scenarios.
    """

    @staticmethod
    def _analyze_single_tf(candles: List[Candle], tf_type: str, tf_label: str) -> Dict:
        if not candles or len(candles) < 5:
            return {
                "tf": tf_label,
                "bias": "NEUTRAL",
                "dealing_range_high": 0.0,
                "dealing_range_low": 0.0,
                "equilibrium": 0.0,
                "zone": "EQUILIBRIUM",
                "erl_bsl": 0.0,
                "erl_ssl": 0.0,
                "irl": "None",
                "prev_high": 0.0,
                "prev_low": 0.0,
                "dol": 0.0,
                "dol_type": "BSL",
                "narrative": "Insufficient historical data for deep liquidity profiling."
            }

        curr = candles[-1]
        prev = candles[-2]
        
        # 1. Dealing Range (last 20 bars)
        lookback = min(len(candles), 25)
        d_bars = candles[-lookback:]
        dr_high = max(c.high for c in d_bars)
        dr_low = min(c.low for c in d_bars)
        eq = (dr_high + dr_low) / 2.0
        
        price = curr.close
        zone = "PREMIUM (Institutional Sell Side)" if price >= eq else "DISCOUNT (Institutional Buy Side)"
        pct_in_range = ((price - dr_low) / (dr_high - dr_low) * 100.0) if dr_high > dr_low else 50.0

        # 2. Key Highs & Lows (PMH/PML, PWH/PWL, PDH/PDL)
        prev_high = prev.high
        prev_low = prev.low

        # 3. ERL (External Range Liquidity = Major Swing Points / BSL & SSL)
        swing_lookback = min(len(candles) - 1, 15)
        recent_highs = [c.high for c in candles[-swing_lookback:-1]]
        recent_lows = [c.low for c in candles[-swing_lookback:-1]]
        erl_bsl = max(recent_highs) if recent_highs else dr_high
        erl_ssl = min(recent_lows) if recent_lows else dr_low

        # 4. IRL (Internal Range Liquidity = Fair Value Gaps inside Range)
        irl_detected = "Balanced Price Action"
        for i in range(len(candles) - 2, max(0, len(candles) - 10), -1):
            c_now = candles[i]
            c_p2 = candles[i - 2]
            if c_now.low > c_p2.high:
                irl_detected = f"Bullish FVG [{c_p2.high:.2f} - {c_now.low:.2f}]"
                break
            elif c_now.high < c_p2.low:
                irl_detected = f"Bearish FVG [{c_now.high:.2f} - {c_p2.low:.2f}]"
                break

        # 5. Market Structure & Liquidity Delivery (ERL to IRL or IRL to ERL)
        # Check if recent candle swept SSL or BSL
        swept_ssl = any(c.low < prev_low and c.close > prev_low for c in candles[-3:])
        swept_bsl = any(c.high > prev_high and c.close < prev_high for c in candles[-3:])

        ema20 = sum(c.close for c in candles[-20:]) / 20.0 if len(candles) >= 20 else eq
        ema50 = sum(c.close for c in candles[-50:]) / 50.0 if len(candles) >= 50 else ema20

        # Structural direction
        is_above_emas = price > ema20 and price > ema50
        is_below_emas = price < ema20 and price < ema50

        if swept_ssl or (is_above_emas and price < eq) or (price > ema20 and curr.close > prev.high):
            bias = "BULLISH"
            dol = erl_bsl
            dol_type = "BSL (Buy-Side Liquidity)"
            narrative = f"Price reacted from {zone} / SSL sweep. Institutional delivery expanding from IRL towards ERL ({dol_type} @ {dol:.2f})."
        elif swept_bsl or (is_below_emas and price > eq) or (price < ema20 and curr.close < prev.low):
            bias = "BEARISH"
            dol = erl_ssl
            dol_type = "SSL (Sell-Side Liquidity)"
            narrative = f"Price reacted from {zone} / BSL sweep. Institutional delivery expanding from IRL towards ERL ({dol_type} @ {dol:.2f})."
        else:
            if price >= eq:
                bias = "BEARISH"
                dol = erl_ssl
                dol_type = "SSL (Internal Sell Draw)"
                narrative = f"Price holding in Premium ({pct_in_range:.0f}%). Potential draw toward equilibrium and SSL @ {dol:.2f}."
            else:
                bias = "BULLISH"
                dol = erl_bsl
                dol_type = "BSL (Internal Buy Draw)"
                narrative = f"Price holding in Discount ({pct_in_range:.0f}%). Potential draw toward equilibrium and BSL @ {dol:.2f}."

        return {
            "tf": tf_label,
            "tf_key": tf_type,
            "bias": bias,
            "current_price": price,
            "dealing_range_high": dr_high,
            "dealing_range_low": dr_low,
            "equilibrium": eq,
            "zone": zone,
            "pct_in_range": pct_in_range,
            "erl_bsl": erl_bsl,
            "erl_ssl": erl_ssl,
            "irl": irl_detected,
            "prev_high": prev_high,
            "prev_low": prev_low,
            "dol": dol,
            "dol_type": dol_type,
            "narrative": narrative
        }

    @classmethod
    def analyze_market_bias(cls, symbol: str, data_feed: DataFeedManager) -> Dict:
        """
        Executes the 4-Timeframe MTF Bias Engine (Monthly + Weekly + Daily + H4).
        """
        # Fetch candles across the 4 key higher timeframes
        candles_m  = data_feed.get_candles(symbol, "1m_month", count=40)
        candles_w  = data_feed.get_candles(symbol, "1w", count=60)
        candles_d  = data_feed.get_candles(symbol, "1d", count=90)
        candles_h4 = data_feed.get_candles(symbol, "4h", count=120)

        # Fallback resampling if MT5 doesn't provide enough monthly/weekly
        if len(candles_m) < 5 and len(candles_d) >= 60:
            # Resample 22 daily bars to monthly
            candles_m = []
            for i in range(0, len(candles_d) - 21, 22):
                chk = candles_d[i:i+22]
                candles_m.append(Candle(chk[0].time, chk[0].open, max(c.high for c in chk), min(c.low for c in chk), chk[-1].close, sum(c.volume for c in chk)))

        if len(candles_w) < 5 and len(candles_d) >= 20:
            # Resample 5 daily bars to weekly
            candles_w = []
            for i in range(0, len(candles_d) - 4, 5):
                chk = candles_d[i:i+5]
                candles_w.append(Candle(chk[0].time, chk[0].open, max(c.high for c in chk), min(c.low for c in chk), chk[-1].close, sum(c.volume for c in chk)))

        # Analyze each timeframe individually
        res_m  = cls._analyze_single_tf(candles_m,  "monthly", "MONTHLY")
        res_w  = cls._analyze_single_tf(candles_w,  "weekly",  "WEEKLY")
        res_d  = cls._analyze_single_tf(candles_d,  "daily",   "DAILY")
        res_h4 = cls._analyze_single_tf(candles_h4, "h4",      "H4")

        # -------------------------------------------------------------
        # Overall MTF Bias Consensus & Hierarchy
        # Priority: 1. Monthly -> 2. Weekly -> 3. Daily -> 4. H4
        # -------------------------------------------------------------
        biases = [res_m["bias"], res_w["bias"], res_d["bias"], res_h4["bias"]]
        bull_count = biases.count("BULLISH")
        bear_count = biases.count("BEARISH")

        # Range / Consolidation Detector across higher and intraday timeframes
        pct_in_daily_range = res_d.get("pct_in_range", 50.0)
        recent_daily_range = (candles_d[-1].high - candles_d[-1].low) if candles_d else 25.0
        avg_daily_range = (sum(c.high - c.low for c in candles_d[-10:]) / min(len(candles_d), 10)) if candles_d else 35.0
        is_ranging = (35.0 <= pct_in_daily_range <= 65.0) and (recent_daily_range < 0.70 * avg_daily_range or bull_count == bear_count)

        digits = 2 if ("XAU" in symbol.upper() or "BTC" in symbol.upper() or "ETH" in symbol.upper()) else 5

        if is_ranging:
            overall_bias = "RANGING / CONSOLIDATION"
            confidence = 65
            action = "SCALP RANGE BOUNDARIES (BUY DISCOUNT / SELL PREMIUM)"
            regime = "CONSOLIDATION (EQUAL HIGHS & LOWS)"
            badge_color = "#f59e0b"
            today_rule = "Aaj market range / consolidation mein hai (No clear HTF trend). Breakouts chase na karein! Sirf Discount Lows par Scalp Buy aur Premium Highs par Scalp Sell karein jab tak Daily candle range se bahar na nikle."
            scalp_advice = "SCALP BOTH SIDES (Range Extremes)"
        elif bull_count == 4:
            overall_bias = "STRONG BUY"
            confidence = 96
            action = "LOOK STRICTLY FOR BUY SIGNALS TODAY"
            regime = "BULLISH EXPANSION (HIGH DEMAND)"
            badge_color = "#10b981"
            today_rule = "Aaj ka din 100% BUY side par hai! Higher Timeframes (Monthly, Weekly, Daily, H4) par Institutional Bullish Order Flow hai. M5/M15 Discount Pullback ya FVG Retest par Buy entry lein. Counter-trend Sell se parhez karein."
            scalp_advice = "LOOK STRICTLY FOR BUY SETUPS"
        elif bull_count == 3:
            overall_bias = "BUY (MODERATE BULLISH)"
            confidence = 82
            action = "BUY FAVORED (ALIGN WITH DOL)"
            regime = "BULLISH REACTION / DISCOUNT EXPANSION"
            badge_color = "#3b82f6"
            today_rule = "Aaj market ka jhukaao BUY ki taraf hai. Discount zones (MSS/OB) par confirmation candle ke sath Buy trades ko priority dein."
            scalp_advice = "BUY ON DIPS (Discount Pullbacks)"
        elif bear_count == 4:
            overall_bias = "STRONG SELL"
            confidence = 96
            action = "LOOK STRICTLY FOR SELL SIGNALS TODAY"
            regime = "BEARISH EXPANSION (HIGH SUPPLY)"
            badge_color = "#ef4444"
            today_rule = "Aaj ka din 100% SELL side par hai! Higher Timeframes (Monthly, Weekly, Daily, H4) par Institutional Bearish Order Flow hai. M5/M15 Premium Pullback ya Bearish FVG Retest par Sell entry lein. Counter-trend Buy se parhez karein."
            scalp_advice = "LOOK STRICTLY FOR SELL SETUPS"
        elif bear_count == 3:
            overall_bias = "SELL (MODERATE BEARISH)"
            confidence = 82
            action = "SELL FAVORED (ALIGN WITH DOL)"
            regime = "BEARISH REACTION / LIQUIDITY DRAW"
            badge_color = "#f97316"
            today_rule = "Aaj market ka jhukaao SELL ki taraf hai. Premium zones (Resistance/OB) par rejection confirmation candle ke sath Sell trades ko priority dein."
            scalp_advice = "SELL ON RALLIES (Premium Pullbacks)"
        else:
            overall_bias = "NEUTRAL / MIXED"
            confidence = 54
            action = "WAIT / STRICT CONFIRMATION REQUIRED"
            regime = "LIQUIDITY ACCUMULATION"
            badge_color = "#eab308"
            today_rule = "HTF aur LTF mein mixed bias hai. A+ Vol Div aur strict confirmation candle ke baghair trade execute na karein."
            scalp_advice = "WAIT OR SELECTIVE SCALP ONLY"

        # Primary Liquidity Target (Draw On Liquidity)
        live_p = data_feed.get_current_price(symbol)
        curr_price = live_p if live_p > 0 else (res_d["current_price"] if res_d["current_price"] > 0 else 3875.65)

        if "BUY" in overall_bias:
            primary_dol = res_d["erl_bsl"]
            secondary_dol = res_w["erl_bsl"]
            invalidation = res_h4["erl_ssl"]
        elif "SELL" in overall_bias:
            primary_dol = res_d["erl_ssl"]
            secondary_dol = res_w["erl_ssl"]
            invalidation = res_h4["erl_bsl"]
        else:
            primary_dol = res_d["erl_bsl"]
            secondary_dol = res_d["erl_ssl"]
            invalidation = res_d["equilibrium"]

        daily_compass = {
            "verdict": overall_bias,
            "badge_color": badge_color,
            "regime": regime,
            "action": action,
            "today_rule": today_rule,
            "scalp_advice": scalp_advice,
            "intraday_bias": f"{res_d['bias']} (H4: {res_h4['bias']})",
            "swing_bias": f"{res_m['bias']} (Weekly: {res_w['bias']})",
            "confidence": confidence,
            "primary_target": f"ERL {('BSL @ ' + str(round(res_d['erl_bsl'], digits))) if 'BUY' in overall_bias else ('SSL @ ' + str(round(res_d['erl_ssl'], digits)) if 'SELL' in overall_bias else 'PDH/PDL Range Ext')}",
            "invalidation_level": round(invalidation, digits)
        }

        # Build Institutional Scenarios
        bullish_scenario = {
            "condition": f"Price holds Discount or sweeps SSL ({res_h4['erl_ssl']:.2f}) with Bullish Displacement & MSS",
            "entry_zone": f"H1/M15 FVG or Breaker Block in Discount",
            "invalidation": f"H4 Candle Body Close below {res_h4['erl_ssl']:.2f}",
            "tp1": f"PDH ({res_d['prev_high']:.2f}) [1:1.5 RR]",
            "tp2": f"Weekly BSL ({primary_dol:.2f}) [1:3.0 RR]"
        }

        bearish_scenario = {
            "condition": f"Price holds Premium or sweeps BSL ({res_h4['erl_bsl']:.2f}) with Bearish Displacement & MSS",
            "entry_zone": f"H1/M15 FVG or Breaker Block in Premium",
            "invalidation": f"H4 Candle Body Close above {res_h4['erl_bsl']:.2f}",
            "tp1": f"PDL ({res_d['prev_low']:.2f}) [1:1.5 RR]",
            "tp2": f"Weekly SSL ({primary_dol:.2f}) [1:3.0 RR]"
        }

        return {
            "symbol": symbol,
            "overall_bias": overall_bias,
            "confidence": confidence,
            "action": action,
            "daily_compass": daily_compass,
            "current_price": curr_price,
            "primary_dol": round(primary_dol, digits),
            "secondary_dol": round(secondary_dol, digits),
            "invalidation": round(invalidation, digits),
            "timeframes": {
                "monthly": res_m,
                "weekly": res_w,
                "daily": res_d,
                "h4": res_h4
            },
            "scenarios": {
                "bullish": bullish_scenario,
                "bearish": bearish_scenario
            },
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
