import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class IDMStructureStrategy(BaseStrategy):
    """
    Strategy 7: SMC Price Action Structure (IDM + First Valid OB & Fibo OTE)
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_idm_structure",
            name="Price Action Structure: IDM + Valid OB (Fibo OTE)",
            description="BOS/CHoCH with body break + IDM sweep + First Valid OB with FVG. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 35:
            return None

        curr = candles[-1]
        prev = candles[-2]

        idm_low  = min(c.low for c in candles[-15:-3])
        idm_high = max(c.high for c in candles[-15:-3])

        valid_bull_ob = None
        valid_bear_ob = None

        for i in range(len(candles) - 20, len(candles) - 2):
            if i < 2:
                continue
            if candles[i].low > candles[i-2].high:
                ob_top = candles[i-2].high
                ob_bot = candles[i-2].low
                if ob_top <= idm_low:
                    valid_bull_ob = {"top": ob_top, "bottom": ob_bot, "bar": i-2}

            if candles[i].high < candles[i-2].low:
                ob_top = candles[i-2].high
                ob_bot = candles[i-2].low
                if ob_bot >= idm_high:
                    valid_bear_ob = {"top": ob_top, "bottom": ob_bot, "bar": i-2}

        # 🟢 BULLISH SETUP:
        idm_swept_bull = any(c.low < idm_low for c in candles[-6:])
        
        if idm_swept_bull and valid_bull_ob:
            ob_top = valid_bull_ob["top"]
            ob_bot = valid_bull_ob["bottom"]

            tested = (curr.low <= ob_top and curr.high >= ob_bot) or (prev.low <= ob_top and prev.high >= ob_bot)
            body_intact = curr.close >= ob_bot and curr.open >= ob_bot

            candle_range = max(curr.high - curr.low, 0.0001)
            lower_wick = min(curr.open, curr.close) - curr.low
            is_rejection = (lower_wick / candle_range) >= 0.35 or (curr.close > curr.open and curr.close > prev.high)

            if tested and body_intact and is_rejection:
                sl = ob_bot - (ob_top - ob_bot) * 0.2
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
                        reason=f"💎 IDM Swept ({idm_low:.2f}) + First Valid OB ({ob_bot:.2f} - {ob_top:.2f}) [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        # 🔴 BEARISH SETUP:
        idm_swept_bear = any(c.high > idm_high for c in candles[-6:])

        if idm_swept_bear and valid_bear_ob:
            ob_top = valid_bear_ob["top"]
            ob_bot = valid_bear_ob["bottom"]

            tested = (curr.high >= ob_bot and curr.low <= ob_top) or (prev.high >= ob_bot and prev.low <= ob_top)
            body_intact = curr.close <= ob_top and curr.open <= ob_top

            candle_range = max(curr.high - curr.low, 0.0001)
            upper_wick = curr.high - max(curr.open, curr.close)
            is_rejection = (upper_wick / candle_range) >= 0.35 or (curr.close < curr.open and curr.close < prev.low)

            if tested and body_intact and is_rejection:
                sl = ob_top + (ob_top - ob_bot) * 0.2
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
                        reason=f"💎 IDM Swept ({idm_high:.2f}) + First Valid OB ({ob_bot:.2f} - {ob_top:.2f}) [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        return None
