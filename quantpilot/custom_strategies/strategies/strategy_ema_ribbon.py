import uuid
import datetime
from typing import List, Optional
from core.models import Candle, Signal
from strategies.base_strategy import BaseStrategy

class EMARibbonStrategy(BaseStrategy):
    """
    Strategy 5: EMA 144 Channel Retest + Fast Ribbon (5, 8, 13, 21) Multi-EMA Cross
    Fixed RR: TP1 = 1:1.5 | TP2 = 1:3.0
    """
    def __init__(self):
        super().__init__(
            strategy_id="strategy_ema_ribbon",
            name="EMA 144 Retest + 5/8/13/21 Cross",
            description="EMA 144 Channel test followed by confirmation candle crossing above/below 5, 8, 13, 21 EMAs. [TP1 1:1.5 | TP2 1:3.0]"
        )

    def evaluate(self, candles: List[Candle], symbol: str, timeframe: str, secondary_candles: Optional[List[Candle]] = None) -> Optional[Signal]:
        if len(candles) < 150:
            return None

        closes = [c.close for c in candles]
        highs  = [c.high for c in candles]
        lows   = [c.low for c in candles]

        ema144_c = self.calc_ema(closes, 144)
        ema144_h = self.calc_ema(highs, 144)
        ema144_l = self.calc_ema(lows, 144)

        ema5  = self.calc_ema(closes, 5)
        ema8  = self.calc_ema(closes, 8)
        ema13 = self.calc_ema(closes, 13)
        ema21 = self.calc_ema(closes, 21)

        curr = candles[-1]
        prev = candles[-2]

        curr_e144_h = ema144_h[-1]
        curr_e144_l = ema144_l[-1]

        curr_e5  = ema5[-1]
        curr_e8  = ema8[-1]
        curr_e13 = ema13[-1]
        curr_e21 = ema21[-1]

        # 🟢 BUY SETUP CHECK:
        tested_144_buy = any(candles[i].low <= ema144_h[i] and candles[i].high >= ema144_l[i] for i in [-3, -2, -1])
        is_green_candle = curr.close > curr.open

        above_all_fast_emas = (curr.close > curr_e5 and 
                               curr.close > curr_e8 and 
                               curr.close > curr_e13 and 
                               curr.close > curr_e21)
        
        crossed_up = prev.close <= ema21[-2] or prev.close <= ema13[-2] or prev.close <= ema8[-2] or prev.close <= ema5[-2]

        if tested_144_buy and is_green_candle and above_all_fast_emas and crossed_up:
            sl = curr_e144_l - (curr.close - curr_e144_l) * 0.15
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
                    reason=f"🚀 EMA 144 Retest + Closed Above 5,8,13,21 EMAs [TP1: 1:1.5 | TP2: 1:3.0]",
                    timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                )

        # 🔴 SELL SETUP CHECK:
        tested_144_sell = any(candles[i].high >= ema144_l[i] and candles[i].low <= ema144_h[i] for i in [-3, -2, -1])
        is_red_candle = curr.close < curr.open

        below_all_fast_emas = (curr.close < curr_e5 and 
                               curr.close < curr_e8 and 
                               curr.close < curr_e13 and 
                               curr.close < curr_e21)
        
        crossed_down = prev.close >= ema21[-2] or prev.close >= ema13[-2] or prev.close >= ema8[-2] or prev.close >= ema5[-2]

        if tested_144_sell and is_red_candle and below_all_fast_emas and crossed_down:
            sl = curr_e144_h + (curr_e144_h - curr.close) * 0.15
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
                    reason=f"🔻 EMA 144 Retest + Closed Below 5,8,13,21 EMAs [TP1: 1:1.5 | TP2: 1:3.0]",
                    timestamp=curr.time.strftime("%Y-%m-%d %H:%M:%S")
                )

        return None
