import datetime
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Candle:
    time: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

@dataclass
class Signal:
    id: str
    strategy_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    action: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    reason: str
    timestamp: str
    status: str = "ACTIVE"                 # "ACTIVE", "TP1_HIT", "WIN (TP2 HIT)", "LOSS (SL HIT)", "EXPIRED"
    vol_div: Optional[str] = None          # Stores Volume Divergence note if confirmed
    is_ultra_strong: bool = False          # True if backed by Vol Div!
    tp1_hit: bool = False
    tp2_hit: bool = False
    sl_hit: bool = False
    closed_at: Optional[str] = None
    closed_price: Optional[float] = None
    result: Optional[str] = None           # "WIN", "LOSS", "EXPIRED"
    pnl_r: Optional[float] = None          # +3.0R or -1.0R
    pnl_pts: Optional[float] = None        # Points/Pips floating or realized
    pnl_usd: Optional[float] = None        # USD dollar amount floating or realized
    live_status_note: Optional[str] = None # e.g. "🎯 TP 1 HIT (1:1.5 RR)! Running to TP 2"
    style: str = "intraday"                # "scalp" (M3-M15), "intraday" (M30-H4), "swing" (1D-1M)

@dataclass
class StrategyStatus:
    id: str
    name: str
    enabled: bool
    description: str
    last_signal_time: Optional[str] = None
