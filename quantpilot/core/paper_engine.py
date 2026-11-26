"""Paper trading engine with break-even at 1R, 50% partial at TP1 and trailing toward TP2."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from .indicators import SPECS
from .models import Position
from .risk import normalize_volume

log = logging.getLogger("quantpilot.paper")


class PaperEngine:
    """Simulated broker. Fills market orders at the given price; manages exits candle by candle."""

    def __init__(self, starting_balance: float) -> None:
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.positions: dict[str, Position] = {}
        self.closed: list[Position] = []
        self.equity_curve: list[dict] = [{"time": int(time.time()), "equity": starting_balance}]

    # ------------------------------------------------------------ queries
    def open_positions(self, instrument: Optional[str] = None) -> list[Position]:
        return [p for p in self.positions.values() if instrument is None or p.instrument == instrument]

    def equity(self) -> float:
        return round(self.balance + sum(p.unrealized_pnl for p in self.positions.values()), 2)

    def open_risk(self) -> float:
        total = 0.0
        for p in self.positions.values():
            spec = SPECS[p.instrument]
            loss = (p.entry_price - p.stop_loss) if p.direction == "LONG" else (p.stop_loss - p.entry_price)
            total += max(0.0, loss) * p.volume * spec.contract_size
        return round(total, 2)

    # ------------------------------------------------------------ orders
    def open(self, *, signal_id: str, instrument: str, direction: str, volume: float, price: float,
             sl: float, tp1: float, tp2: float, ts: Optional[float] = None) -> Position:
        pos = Position(
            id=uuid.uuid4().hex[:10], signal_id=signal_id, instrument=instrument, direction=direction,  # type: ignore[arg-type]
            volume=volume, initial_volume=volume, entry_price=price, stop_loss=sl, initial_stop=sl,
            take_profit_1=tp1, take_profit_2=tp2, opened_at=ts or time.time(),
        )
        self.positions[pos.id] = pos
        log.info("PAPER open %s %s %.2f @ %.2f SL %.2f TP1 %.2f TP2 %.2f", instrument, direction, volume, price, sl, tp1, tp2)
        return pos

    def _pnl(self, pos: Position, price: float, volume: float) -> float:
        sign = 1 if pos.direction == "LONG" else -1
        return (price - pos.entry_price) * sign * volume * SPECS[pos.instrument].contract_size

    def _close(self, pos: Position, price: float, reason: str, ts: float) -> None:
        pnl = self._pnl(pos, price, pos.volume)
        self.balance += pnl
        pos.realized_pnl = round(pos.realized_pnl + pnl, 2)
        pos.unrealized_pnl = 0.0
        pos.status, pos.exit_price, pos.closed_at, pos.close_reason = "closed", price, ts, reason
        self.positions.pop(pos.id, None)
        self.closed.append(pos)

    def close_all(self, prices: dict[str, float], reason: str = "Kill switch") -> list[Position]:
        out = []
        for pos in list(self.positions.values()):
            self._close(pos, prices.get(pos.instrument, pos.entry_price), reason, time.time())
            out.append(pos)
        return out

    # ------------------------------------------------------------ candle update
    def on_candle(self, instrument: str, candle: dict) -> list[dict]:
        """Apply one closed candle to open positions. Returns lifecycle events for the UI."""
        events: list[dict] = []
        hi, lo, close, ts = candle["high"], candle["low"], candle["close"], float(candle["time"])
        for pos in list(self.positions.values()):
            if pos.instrument != instrument:
                continue
            spec = SPECS[instrument]
            long_ = pos.direction == "LONG"
            r = abs(pos.entry_price - pos.initial_stop)
            adverse = lo if long_ else hi
            favorable = hi if long_ else lo
            # conservative: stop is assumed hit before targets inside the same candle
            if (long_ and adverse <= pos.stop_loss) or (not long_ and adverse >= pos.stop_loss):
                reason = "Break-even stop" if pos.breakeven and abs(pos.stop_loss - pos.entry_price) < 1e-9 else ("Trailing stop" if pos.tp1_hit else "Stop loss")
                self._close(pos, pos.stop_loss, reason, ts)
                events.append({"type": "sl" if reason == "Stop loss" else "stop", "position": pos.model_dump(), "reason": reason})
                continue
            reached = lambda lvl: (favorable >= lvl) if long_ else (favorable <= lvl)  # noqa: E731
            if not pos.breakeven and reached(pos.entry_price + (r if long_ else -r)):
                pos.stop_loss = pos.entry_price
                pos.breakeven = True
                events.append({"type": "be", "position": pos.model_dump()})
            if not pos.tp1_hit and reached(pos.take_profit_1):
                half = normalize_volume(pos.volume / 2, spec.volume_min, spec.volume_step, pos.volume)
                pos.tp1_hit = True
                if 0 < half < pos.volume:
                    pnl = self._pnl(pos, pos.take_profit_1, half)
                    self.balance += pnl
                    pos.realized_pnl = round(pos.realized_pnl + pnl, 2)
                    pos.volume = round(pos.volume - half, 2)
                pos.stop_loss = pos.entry_price if not pos.breakeven else pos.stop_loss
                pos.breakeven = True
                events.append({"type": "tp1", "position": pos.model_dump()})
            if pos.tp1_hit:
                trail = close - r if long_ else close + r
                if (long_ and trail > pos.stop_loss) or (not long_ and trail < pos.stop_loss):
                    pos.stop_loss = round(trail, spec.digits)
            if reached(pos.take_profit_2):
                self._close(pos, pos.take_profit_2, "TP2", ts)
                events.append({"type": "tp2", "position": pos.model_dump()})
                continue
            pos.unrealized_pnl = round(self._pnl(pos, close, pos.volume), 2)
        self.equity_curve.append({"time": int(ts), "equity": self.equity()})
        if len(self.equity_curve) > 3000:
            self.equity_curve = self.equity_curve[-2500:]
        return events
