import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class SMCStructureIDMEXTStrategy(BaseStrategy):
    """
    Strategy 8: SMC Market Structure (SMC IDM + IDM OB & EXT OB)
    Rules:
    - Tracks SMC Market Structure (BOS / CHoCH)
    - Detects SMC IDM (Inducement) Sweep
    - Identifies:
      1. IDM OB: First valid Order Block with FVG after the IDM.
      2. EXT OB: Extreme Order Block with FVG at the origin of the wave.
    - Confirms with Rejection / Engulfing candle.
    - Targets (User Rules):
      TP 1 = 1:1.5 Risk-to-Reward
      TP 2 = 1:3.0 Risk-to-Reward
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_smc_structure_idm_ext",
            name="SMC Structure: IDM OB & EXT OB",
            description="SMC Structure with IDM sweep. Triggers on IDM OB or EXT OB retest with TP1 (1:1.5 RR) and TP2 (1:3.0 RR)."
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 40:
            return None

        curr = candles[-1]
        prev = candles[-2]

        # Structure lookback
        lookback = min(len(candles) - 5, 50)
        swing_high = max(c.high for c in candles[-lookback:-5])
        swing_low  = min(c.low for c in candles[-lookback:-5])

        # SMC IDM (Inducement): the most recent pullback swing point
        idm_low  = min(c.low for c in candles[-15:-3])
        idm_high = max(c.high for c in candles[-15:-3])

        # Scan for IDM OB and EXT OB
        idm_bull_ob = None
        ext_bull_ob = None
        idm_bear_ob = None
        ext_bear_ob = None

        # 1. Bullish Zones (Demand)
        for i in range(len(candles) - 25, len(candles) - 2):
            if i < 2:
                continue
            # Order block with FVG
            if candles[i].low > candles[i-2].high:
                top = candles[i-2].high
                bot = candles[i-2].low
                # IDM OB: closest valid OB below IDM
                if top <= idm_low:
                    if idm_bull_ob is None:
                        idm_bull_ob = {"top": top, "bottom": bot, "type": "IDM OB (First Valid)"}
                # EXT OB: extreme lowest valid OB near wave origin
                if bot <= swing_low + (swing_high - swing_low) * 0.20:
                    ext_bull_ob = {"top": top, "bottom": bot, "type": "EXT OB (Extreme Origin)"}

        # 2. Bearish Zones (Supply)
        for i in range(len(candles) - 25, len(candles) - 2):
            if i < 2:
                continue
            if candles[i].high < candles[i-2].low:
                top = candles[i-2].high
                bot = candles[i-2].low
                # IDM OB: closest valid OB above IDM
                if bot >= idm_high:
                    if idm_bear_ob is None:
                        idm_bear_ob = {"top": top, "bottom": bot, "type": "IDM OB (First Valid)"}
                # EXT OB: extreme highest valid OB near wave origin
                if top >= swing_high - (swing_high - swing_low) * 0.20:
                    ext_bear_ob = {"top": top, "bottom": bot, "type": "EXT OB (Extreme Origin)"}

        # 🟢 BULLISH SMC SETUP (IDM Swept + IDM OB or EXT OB Test)
        idm_swept_bull = any(c.low < idm_low for c in candles[-6:])

        if idm_swept_bull:
            target_obs = [ob for ob in [ext_bull_ob, idm_bull_ob] if ob is not None]
            for ob in target_obs:
                top = ob["top"]
                bot = ob["bottom"]
                ob_type = ob["type"]

                # Retest of zone or 50% middle line
                tested = (curr.low <= top and curr.high >= bot) or (prev.low <= top and prev.high >= bot)
                body_intact = curr.close >= bot and curr.open >= bot

                candle_range = max(curr.high - curr.low, 0.0001)
                lower_wick = min(curr.open, curr.close) - curr.low
                is_rejection = (lower_wick / candle_range) >= 0.35 or (curr.close > curr.open and curr.close > prev.high)

                if tested and body_intact and is_rejection:
                    sl = bot - (top - bot) * 0.15
                    risk = curr.close - sl
                    if risk > 0:
                        # User Rules: TP1 = 1:1.5 RR, TP2 = 1:3.0 RR
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
                            reason=f"🔥 SMC Structure: IDM Swept ({idm_low:.2f}) + {ob_type} Retest ({bot:.2f} - {top:.2f}) with Rejection [TP1 1:1.5 | TP2 1:3]",
                            timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                        )

        # 🔴 BEARISH SMC SETUP (IDM Swept + IDM OB or EXT OB Test)
        idm_swept_bear = any(c.high > idm_high for c in candles[-6:])

        if idm_swept_bear:
            target_obs = [ob for ob in [ext_bear_ob, idm_bear_ob] if ob is not None]
            for ob in target_obs:
                top = ob["top"]
                bot = ob["bottom"]
                ob_type = ob["type"]

                tested = (curr.high >= bot and curr.low <= top) or (prev.high >= bot and prev.low <= top)
                body_intact = curr.close <= top and curr.open <= top

                candle_range = max(curr.high - curr.low, 0.0001)
                upper_wick = curr.high - max(curr.open, curr.close)
                is_rejection = (upper_wick / candle_range) >= 0.35 or (curr.close < curr.open and curr.close < prev.low)

                if tested and body_intact and is_rejection:
                    sl = top + (top - bot) * 0.15
                    risk = sl - curr.close
                    if risk > 0:
                        # User Rules: TP1 = 1:1.5 RR, TP2 = 1:3.0 RR
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
                            reason=f"🔥 SMC Structure: IDM Swept ({idm_high:.2f}) + {ob_type} Retest ({bot:.2f} - {top:.2f}) with Rejection [TP1 1:1.5 | TP2 1:3]",
                            timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                        )

        return None
