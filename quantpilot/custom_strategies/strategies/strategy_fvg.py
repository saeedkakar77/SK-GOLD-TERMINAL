import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class FVGStrategy(BaseStrategy):
    """
    Strategy 2: Fair Value Gap (FVG) Retest & 50% CE Bounce
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_fvg",
            name="Fair Value Gap (FVG) Retest",
            description="Institutional Imbalance. Triggers when price tests 50% FVG zone and confirms. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 20:
            return None

        atrs = self.calc_atr(candles, period=14)
        atr = atrs[-1] if atrs else 0.0
        min_gap = atr * 0.4 if atr > 0 else 0.0

        curr = candles[-1]
        prev = candles[-2]

        active_bull_fvg = None
        active_bear_fvg = None

        for i in range(len(candles) - 15, len(candles) - 1):
            if i < 2:
                continue
            gap_bull = candles[i].low - candles[i-2].high
            if gap_bull >= min_gap:
                top = candles[i].low
                bot = candles[i-2].high
                mid = (top + bot) / 2.0
                active_bull_fvg = {"top": top, "bottom": bot, "ce": mid, "bar": i}

            gap_bear = candles[i-2].low - candles[i].high
            if gap_bear >= min_gap:
                top = candles[i-2].low
                bot = candles[i].high
                mid = (top + bot) / 2.0
                active_bear_fvg = {"top": top, "bottom": bot, "ce": mid, "bar": i}

        if active_bull_fvg:
            top = active_bull_fvg["top"]
            bot = active_bull_fvg["bottom"]
            ce = active_bull_fvg["ce"]

            retested = (curr.low <= top and curr.low >= bot) or (prev.low <= top and prev.low >= bot)
            body_held = curr.close > bot and curr.open > bot
            green_close = curr.close > curr.open and curr.close >= ce

            if retested and body_held and green_close:
                sl = bot - (top - bot) * 0.2
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
                        reason=f"Bullish FVG+ ({bot:.2f} - {top:.2f}) 50% CE Bounce [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        if active_bear_fvg:
            top = active_bear_fvg["top"]
            bot = active_bear_fvg["bottom"]
            ce = active_bear_fvg["ce"]

            retested = (curr.high >= bot and curr.high <= top) or (prev.high >= bot and prev.high <= top)
            body_held = curr.close < top and curr.open < top
            red_close = curr.close < curr.open and curr.close <= ce

            if retested and body_held and red_close:
                sl = top + (top - bot) * 0.2
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
                        reason=f"Bearish FVG- ({bot:.2f} - {top:.2f}) 50% CE Drop [TP1: 1:1.5 | TP2: 1:3.0]",
                        timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                    )

        return None
