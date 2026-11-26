"""MetaTrader 5 live execution bridge.

Every public method is synchronous and guarded by a lock (the MetaTrader5 package
is not thread-safe); the async layer calls them via ``asyncio.to_thread``.

Safety properties enforced here (not in the UI):
* orders are refused on non-DEMO accounts unless live trading was explicitly unlocked;
* one signal_id can create at most one order (DB-backed claim, survives restarts);
* ``order_check`` must pass before ``order_send`` is called;
* SL/TP are validated against the symbol's stops and freeze levels.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from .db import Database
from .risk import normalize_volume

log = logging.getLogger("quantpilot.mt5")

RETCODE_TEXT: dict[int, str] = {
    10004: "Requote: price changed. Retrying with a fresh price.",
    10006: "Request rejected by the broker.",
    10007: "Request cancelled by trader.",
    10008: "Order placed.",
    10009: "Request completed.",
    10010: "Partially filled.",
    10011: "Request processing error.",
    10012: "Request timed out.",
    10013: "Invalid request.",
    10014: "Invalid volume for this symbol.",
    10015: "Invalid price.",
    10016: "Invalid stops: SL/TP too close to price or on the wrong side.",
    10017: "Trading is disabled for this symbol/account.",
    10018: "Market is closed.",
    10019: "Not enough money to open this position.",
    10020: "Prices changed.",
    10021: "No quotes to process the request.",
    10024: "Too many requests: slow down.",
    10026: "Autotrading disabled by the server.",
    10027: "Algo Trading is disabled in the terminal: click the 'Algo Trading' button so it turns green.",
    10030: "Unsupported filling mode for this symbol.",
    10031: "No connection to the trade server.",
    10040: "Position limit reached.",
    10044: "Only position closing is allowed for this symbol.",
}
OK_SEND = {10008, 10009, 10010}


def retcode_message(code: Optional[int]) -> str:
    if code is None:
        return "No response from terminal."
    return RETCODE_TEXT.get(int(code), f"Broker returned code {code}.")


@dataclass
class OrderResult:
    ok: bool
    message: str
    retcode: Optional[int] = None
    ticket: Optional[int] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    symbol: Optional[str] = None
    duplicate: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _load_mt5() -> Any:
    if sys.platform != "win32":
        return None
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5
    except ImportError:
        return None


class MT5Bridge:
    """Connection, health, symbol mapping, order flow, position management and sync for MT5."""

    DEFAULT_MAP = {"XAUUSD": "XAUUSD", "BTCUSD": "BTCUSD"}

    def __init__(self, db: Database, *, login: int, password: str, server: str, path: str, magic: int,
                 deviation: int = 20, mt5_module: Any = None, allow_live_env: bool = False,
                 on_event: Optional[Callable[[str, dict], None]] = None) -> None:
        self.db = db
        self._login, self._password, self._server, self._path = login, password, server, path
        self.magic = magic
        self.deviation = deviation
        self.mt5 = mt5_module if mt5_module is not None else _load_mt5()
        self.allow_live_env = allow_live_env
        self.live_unlocked = False
        self.on_event = on_event or (lambda kind, payload: None)
        self._lock = threading.RLock()
        self.connected = False
        self.login_error = ""
        self.last_health: dict = {}
        self.symbol_map: dict[str, str] = {**self.DEFAULT_MAP, **(db.kv_get("mt5_symbol_map", {}) or {})}
        self.meta: dict[str, dict] = db.kv_get("mt5_position_meta", {}) or {}
        self._last_order_ts: dict[str, float] = {}

    # ================================================================ connection / health
    @property
    def available(self) -> bool:
        return self.mt5 is not None

    def unavailable_reason(self) -> str:
        if sys.platform != "win32":
            return "MetaTrader 5's Python API runs only on Windows. QUANT PILOT stays in Demo/Paper mode on this OS."
        return "MetaTrader5 Python package is not installed. Run: pip install MetaTrader5"

    def connect(self) -> bool:
        """Initialize the terminal connection. Never logs the password."""
        if not self.available:
            self.connected = False
            return False
        with self._lock:
            # 1) attach to the terminal
            ok = bool(self.mt5.initialize(path=self._path) if self._path else self.mt5.initialize())
            self.connected = ok
            self.login_error = ""
            if not ok:
                log.warning("MT5 initialize failed: %s", self._safe_error())
                return False
            # 2) make sure the configured account is the one logged in (login is attempted once per connect)
            if self._login and self._password and self._server:
                acc = self.mt5.account_info()
                if acc is None or int(acc.login) != int(self._login):
                    if not self.mt5.login(int(self._login), password=self._password, server=self._server):
                        self.login_error = self._safe_error()
                        log.warning("MT5 login to configured account failed: %s", self.login_error)
            acc = self.mt5.account_info()
            log.info("MT5 connected (account=%s server=%s)", getattr(acc, "login", "?"), getattr(acc, "server", "?"))
            return True

    @property
    def account_mismatch(self) -> bool:
        """True when .env names an account that is not the one logged in to the terminal."""
        acc = self.last_health.get("account") or {}
        return bool(self._login) and bool(acc) and int(acc.get("login", 0)) != int(self._login)

    def shutdown(self) -> None:
        if self.available:
            with self._lock:
                try:
                    self.mt5.shutdown()
                except Exception:  # noqa: BLE001 - shutdown must never raise
                    pass
        self.connected = False

    def _safe_error(self) -> str:
        try:
            code, msg = self.mt5.last_error()
            return f"{code}: {msg}"
        except Exception:  # noqa: BLE001
            return "unknown error"

    def health(self) -> dict:
        """Full readiness report with human-readable fixes for every failed check."""
        issues: list[dict] = []
        out: dict[str, Any] = {"available": self.available, "connected": False, "issues": issues, "checked_at": time.time(),
                               "symbol_map": self.symbol_map, "live_unlocked": self.live_unlocked,
                               "allow_live_env": self.allow_live_env}
        if not self.available:
            issues.append({"code": "unavailable", "message": self.unavailable_reason(), "fix": self.unavailable_reason()})
            self.last_health = out
            return out
        with self._lock:
            term = self.mt5.terminal_info() if self.connected else None
            if term is None:
                self.connect()
                term = self.mt5.terminal_info() if self.connected else None
            if term is None:
                self.connected = False
                issues.append({"code": "terminal", "message": f"Cannot reach the MT5 terminal ({self._safe_error()}).",
                               "fix": "Open MetaTrader 5, log in to your account, and check MT5_PATH in .env."})
                self.last_health = out
                return out
            acc = self.mt5.account_info()
            out["connected"] = acc is not None
            out["terminal"] = {"name": getattr(term, "name", ""), "company": getattr(term, "company", ""),
                               "trade_allowed": bool(getattr(term, "trade_allowed", False)),
                               "connected": bool(getattr(term, "connected", True))}
            out["ping_ms"] = round(getattr(term, "ping_last", 0) / 1000.0, 1)
            if not getattr(term, "connected", True):
                issues.append({"code": "server", "message": "Terminal is not connected to the trade server.",
                               "fix": "Check your internet connection and the server name in MT5 (bottom-right status)."})
            if not getattr(term, "trade_allowed", False):
                issues.append({"code": "algo", "message": "Algo Trading is disabled in the terminal.",
                               "fix": "Click the 'Algo Trading' button in the MT5 toolbar so it turns green."})
            if acc is None:
                issues.append({"code": "account", "message": "No account is logged in.",
                               "fix": "File > Login to Trade Account in MT5, or set MT5_LOGIN / MT5_SERVER in .env."})
            else:
                mode = {0: "DEMO", 1: "CONTEST", 2: "REAL"}.get(getattr(acc, "trade_mode", 2), "REAL")
                out["account"] = {"login": acc.login, "name": acc.name, "server": acc.server, "currency": acc.currency,
                                  "balance": acc.balance, "equity": acc.equity, "margin_free": getattr(acc, "margin_free", 0.0),
                                  "leverage": getattr(acc, "leverage", 0), "trade_mode": mode,
                                  "trade_allowed": bool(getattr(acc, "trade_allowed", False))}
                if not getattr(acc, "trade_allowed", False):
                    issues.append({"code": "account_trade", "message": "Trading is not allowed for this account.",
                                   "fix": "Log in with the master (trading) password, not the investor password."})
                if self._login and int(acc.login) != int(self._login):
                    why = f" Login error: {self.login_error}." if getattr(self, "login_error", "") else ""
                    issues.append({"code": "account_mismatch",
                                   "message": f"Terminal is logged in to {acc.login} @ {acc.server}, not the configured {self._login} @ {self._server}.{why}",
                                   "fix": f"In MT5 use File > Login to Trade Account with {self._login} on {self._server} "
                                          "(check the password and that the server is listed), or set MT5_LOGIN / MT5_SERVER in .env "
                                          "to the account you want, then press Reconnect. Orders stay blocked until they match."})
            syms: dict[str, bool] = {}
            for inst, sym in self.symbol_map.items():
                ok = bool(self.mt5.symbol_select(sym, True))
                syms[inst] = ok
                if not ok:
                    issues.append({"code": f"symbol_{inst}", "message": f"Symbol '{sym}' is not available at this broker.",
                                   "fix": f"Open Settings > Symbol mapping and choose the broker's name for {inst}."})
            out["symbols"] = syms
        self.last_health = out
        return out

    def is_ready(self) -> bool:
        h = self.last_health
        return bool(h.get("connected")) and not any(
            i["code"] in ("algo", "account_trade", "terminal", "account_mismatch") for i in h.get("issues", []))

    def account_mode(self) -> Optional[str]:
        return (self.last_health.get("account") or {}).get("trade_mode")

    # ================================================================ symbols / data
    def detect_symbols(self) -> dict[str, list[str]]:
        """Candidate broker symbol names for each instrument (e.g. XAUUSD, XAUUSDm, GOLD)."""
        if not self.connected:
            return {"XAUUSD": [], "BTCUSD": []}
        with self._lock:
            names = [s.name for s in (self.mt5.symbols_get() or [])]
        xau = [n for n in names if "XAU" in n.upper() and "USD" in n.upper() or n.upper().startswith("GOLD")]
        btc = [n for n in names if "BTC" in n.upper() and "USD" in n.upper()]
        key = lambda n: (len(n), n)  # noqa: E731 - shortest (canonical) names first
        return {"XAUUSD": sorted(xau, key=key)[:12], "BTCUSD": sorted(btc, key=key)[:12]}

    def set_symbol_map(self, mapping: dict[str, str]) -> None:
        self.symbol_map.update({k: v for k, v in mapping.items() if k in self.DEFAULT_MAP and v})
        self.db.kv_set("mt5_symbol_map", self.symbol_map)

    def sym(self, instrument: str) -> str:
        return self.symbol_map.get(instrument, instrument)

    def rates(self, instrument: str, timeframe: str = "M5", count: int = 2500) -> list[dict]:
        """Closed candles (the forming bar is excluded)."""
        with self._lock:
            tf = getattr(self.mt5, f"TIMEFRAME_{timeframe}")
            sym = self.sym(instrument)
            self.mt5.symbol_select(sym, True)
            arr = self.mt5.copy_rates_from_pos(sym, tf, 1, count)
        if arr is None:
            return []
        return [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
                 "close": float(r["close"]), "volume": float(r["tick_volume"])} for r in arr]

    def symbol_snapshot(self, instrument: str) -> Optional[dict]:
        with self._lock:
            info = self.mt5.symbol_info(self.sym(instrument))
            tick = self.mt5.symbol_info_tick(self.sym(instrument))
        if info is None:
            return None
        return {"spread_points": float(info.spread), "point": info.point, "digits": info.digits,
                "tick_value": getattr(info, "trade_tick_value", None), "tick_size": getattr(info, "trade_tick_size", None),
                "volume_min": info.volume_min, "volume_step": info.volume_step, "volume_max": info.volume_max,
                "contract_size": getattr(info, "trade_contract_size", 1.0),
                "bid": getattr(tick, "bid", None), "ask": getattr(tick, "ask", None)}

    # ================================================================ order helpers
    def normalize_volume(self, info: Any, volume: float) -> float:
        return normalize_volume(volume, info.volume_min, info.volume_step, info.volume_max)

    def validate_stops(self, info: Any, direction: str, price: float, sl: float, tp: float) -> tuple[bool, float, float, str]:
        """Check SL/TP against side, stops level and freeze level. TP may be pushed out; SL is never moved."""
        pt = info.point
        min_dist = max(getattr(info, "trade_stops_level", 0), getattr(info, "trade_freeze_level", 0)) * pt
        digits = info.digits
        if direction == "LONG":
            if not sl < price:
                return False, sl, tp, f"Stop loss {sl} must be below the buy price {price}."
            if not tp > price:
                return False, sl, tp, f"Take profit {tp} must be above the buy price {price}."
            if price - sl < min_dist:
                return False, sl, tp, f"Stop loss is {round((price - sl) / pt)} pts from price; broker minimum is {round(min_dist / pt)} pts."
            note = ""
            if tp - price < min_dist:
                tp = round(price + min_dist, digits)
                note = f"TP moved to broker minimum distance ({tp})."
        else:
            if not sl > price:
                return False, sl, tp, f"Stop loss {sl} must be above the sell price {price}."
            if not tp < price:
                return False, sl, tp, f"Take profit {tp} must be below the sell price {price}."
            if sl - price < min_dist:
                return False, sl, tp, f"Stop loss is {round((sl - price) / pt)} pts from price; broker minimum is {round(min_dist / pt)} pts."
            note = ""
            if price - tp < min_dist:
                tp = round(price - min_dist, digits)
                note = f"TP moved to broker minimum distance ({tp})."
        return True, round(sl, digits), round(tp, digits), note or "Stops valid."

    def filling_modes(self, info: Any) -> list[int]:
        """Filling modes to try, in order FOK, IOC, RETURN, filtered by the symbol's allowed flags."""
        flags = int(getattr(info, "filling_mode", 0) or 0)
        modes: list[int] = []
        if flags & 1:
            modes.append(self.mt5.ORDER_FILLING_FOK)
        if flags & 2:
            modes.append(self.mt5.ORDER_FILLING_IOC)
        modes.append(self.mt5.ORDER_FILLING_RETURN)
        # if the broker reports no flags, still try all three
        for m in (self.mt5.ORDER_FILLING_FOK, self.mt5.ORDER_FILLING_IOC):
            if m not in modes:
                modes.append(m)
        return modes

    def _emit_log(self, kind: str, symbol: str, retcode: Optional[int], ticket: Optional[int], price: Optional[float],
                  volume: Optional[float], message: str, request: Optional[dict] = None) -> None:
        row = self.db.log_mt5(kind, symbol, retcode, ticket, price, volume, message, request)
        self.on_event("mt5_log", row)

    def _check_and_send(self, request: dict, info: Any) -> tuple[Any, str]:
        """Try filling modes until order_check passes, then order_send (one requote retry)."""
        last_msg = "order_check failed"
        for mode in self.filling_modes(info):
            req = {**request, "type_filling": mode}
            chk = self.mt5.order_check(req)
            code = getattr(chk, "retcode", None)
            if chk is None or code not in (0, 10009):
                last_msg = f"order_check: {getattr(chk, 'comment', '') or retcode_message(code)}"
                if code == 10030 or (chk is not None and "filling" in str(getattr(chk, "comment", "")).lower()):
                    continue  # try next filling mode
                return chk, last_msg
            res = self.mt5.order_send(req)
            if res is not None and res.retcode in (10004, 10020):  # requote / price changed
                tick = self.mt5.symbol_info_tick(req["symbol"])
                req["price"] = tick.ask if req["type"] == self.mt5.ORDER_TYPE_BUY else tick.bid
                res = self.mt5.order_send(req)
            return res, retcode_message(getattr(res, "retcode", None))
        return None, last_msg

    # ================================================================ order flow
    def place_order(self, *, signal_id: str, instrument: str, direction: str, volume: float, sl: float,
                    tp1: float, tp2: float, cooldown_s: float = 60.0) -> OrderResult:
        """Place a Guardian-approved market order. Idempotent by signal_id."""
        sym = self.sym(instrument)
        if not self.available or not self.connected:
            return OrderResult(False, "MT5 is not connected.", symbol=sym)
        mode = self.account_mode()
        if mode != "DEMO" and not (self.allow_live_env and self.live_unlocked):
            msg = (f"Refused: account is {mode or 'UNKNOWN'}, and QUANT PILOT is in DEMO ACCOUNT ONLY mode. "
                   "Enable Live in Settings and type the confirmation phrase.")
            self._emit_log("refused", sym, None, None, None, volume, msg)
            return OrderResult(False, msg, symbol=sym)
        last = self._last_order_ts.get(instrument, 0.0)
        if time.time() - last < cooldown_s:
            return OrderResult(False, f"Cooldown: last {instrument} order was {int(time.time() - last)}s ago.", symbol=sym)

        with self._lock:
            info = self.mt5.symbol_info(sym)
            tick = self.mt5.symbol_info_tick(sym)
            if info is None or tick is None:
                return OrderResult(False, f"No symbol info / quotes for {sym}.", symbol=sym)
            vol = self.normalize_volume(info, volume)
            if vol <= 0:
                return OrderResult(False, f"Volume {volume} is below the symbol minimum {info.volume_min}.", symbol=sym)
            buy = direction == "LONG"
            price = tick.ask if buy else tick.bid
            ok, sl_v, tp_v, note = self.validate_stops(info, direction, price, sl, tp2)
            if not ok:
                self._emit_log("rejected", sym, None, None, price, vol, note)
                return OrderResult(False, note, symbol=sym, price=price, volume=vol)
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": vol,
                "type": self.mt5.ORDER_TYPE_BUY if buy else self.mt5.ORDER_TYPE_SELL,
                "price": price, "sl": sl_v, "tp": tp_v, "deviation": self.deviation, "magic": self.magic,
                "comment": f"QuantPilot|{signal_id}"[:31], "type_time": self.mt5.ORDER_TIME_GTC,
            }
            if not self.db.claim_signal(signal_id, request):
                prev = self.db.signal_order(signal_id) or {}
                return OrderResult(False, f"Signal {signal_id} already executed (ticket {prev.get('ticket')}).",
                                   ticket=prev.get("ticket"), symbol=sym, duplicate=True)
            res, msg = self._check_and_send(request, info)
            code = getattr(res, "retcode", None)
            if res is None or code not in OK_SEND:
                full = f"{msg}{' ' + note if 'moved' in note else ''}"
                self.db.finish_signal(signal_id, "failed", code, full, None, None)
                self._emit_log("order_failed", sym, code, None, price, vol, full, request)
                return OrderResult(False, full, retcode=code, symbol=sym, price=price, volume=vol)
            fill_price = float(getattr(res, "price", 0.0) or price)
            ticket = self._find_position_ticket(sym, signal_id) or int(getattr(res, "order", 0) or 0) or None
            self.db.finish_signal(signal_id, "filled", code, msg, ticket, fill_price)
            self._last_order_ts[instrument] = time.time()
            self.meta[str(ticket)] = {"signal_id": signal_id, "instrument": instrument, "direction": direction,
                                      "entry": fill_price, "initial_sl": sl_v, "tp1": tp1, "tp2": tp_v,
                                      "initial_volume": vol, "be": False, "tp1_hit": False}
            self.db.kv_set("mt5_position_meta", self.meta)
            self._emit_log("order_filled", sym, code, ticket, fill_price, vol, f"Trade placed on MT5 · Ticket #{ticket}", request)
            return OrderResult(True, f"Trade placed on MT5 · Ticket #{ticket}", retcode=code, ticket=ticket,
                               price=fill_price, volume=vol, symbol=sym)

    def _find_position_ticket(self, sym: str, signal_id: str) -> Optional[int]:
        for _ in range(5):
            positions = self.mt5.positions_get(symbol=sym) or []
            mine = [p for p in positions if p.magic == self.magic and signal_id[:20] in (p.comment or "")]
            if not mine:
                mine = [p for p in positions if p.magic == self.magic]
            if mine:
                return int(max(mine, key=lambda p: p.time).ticket)
            time.sleep(0.2)
        return None

    def close_position(self, ticket: int, volume: Optional[float] = None, reason: str = "Close") -> OrderResult:
        """Close all or part of a position with an opposite deal referencing the position ticket."""
        with self._lock:
            pos_list = self.mt5.positions_get(ticket=int(ticket)) or []
            if not pos_list:
                return OrderResult(False, f"Position #{ticket} not found.")
            p = pos_list[0]
            info = self.mt5.symbol_info(p.symbol)
            tick = self.mt5.symbol_info_tick(p.symbol)
            vol = self.normalize_volume(info, volume) if volume else p.volume
            if vol <= 0:
                return OrderResult(False, "Partial volume below the symbol minimum.")
            is_buy = p.type == self.mt5.POSITION_TYPE_BUY
            request = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": vol, "position": int(ticket),
                       "type": self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY,
                       "price": tick.bid if is_buy else tick.ask, "deviation": self.deviation, "magic": self.magic,
                       "comment": f"QP|{reason}"[:31], "type_time": self.mt5.ORDER_TIME_GTC}
            res, msg = self._check_and_send(request, info)
            code = getattr(res, "retcode", None)
            ok = res is not None and code in OK_SEND
            self._emit_log("close" if ok else "close_failed", p.symbol, code, int(ticket), getattr(res, "price", None), vol,
                           f"{reason}: {msg}", request)
            return OrderResult(ok, f"{reason}: {msg}", retcode=code, ticket=int(ticket), price=getattr(res, "price", None),
                               volume=vol, symbol=p.symbol)

    def modify_sl(self, ticket: int, sl: float, tp: float, reason: str) -> OrderResult:
        with self._lock:
            pos_list = self.mt5.positions_get(ticket=int(ticket)) or []
            if not pos_list:
                return OrderResult(False, f"Position #{ticket} not found.")
            p = pos_list[0]
            request = {"action": self.mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": int(ticket),
                       "sl": sl, "tp": tp, "magic": self.magic}
            res = self.mt5.order_send(request)
            code = getattr(res, "retcode", None)
            ok = res is not None and code in OK_SEND
            self._emit_log("modify" if ok else "modify_failed", p.symbol, code, int(ticket), sl, p.volume,
                           f"{reason}: {retcode_message(code)}", request)
            return OrderResult(ok, reason, retcode=code, ticket=int(ticket))

    def manage_positions(self) -> list[dict]:
        """Break-even at 1R, 50% partial at TP1, trail the remainder toward TP2."""
        events: list[dict] = []
        if not self.connected:
            return events
        with self._lock:
            positions = [p for p in (self.mt5.positions_get() or []) if p.magic == self.magic]
        for p in positions:
            m = self.meta.get(str(p.ticket))
            if not m:
                continue
            long_ = m["direction"] == "LONG"
            r = abs(m["entry"] - m["initial_sl"])
            if r <= 0:
                continue
            px = p.price_current
            gain = (px - m["entry"]) if long_ else (m["entry"] - px)
            if not m["be"] and gain >= r:
                if self.modify_sl(p.ticket, round(m["entry"], 5), p.tp, "Break-even at 1R").ok:
                    m["be"] = True
                    events.append({"type": "be", "ticket": p.ticket})
            hit_tp1 = (px >= m["tp1"]) if long_ else (px <= m["tp1"])
            if not m["tp1_hit"] and hit_tp1:
                half = p.volume / 2
                res = self.close_position(p.ticket, half, "Partial 50% at TP1")
                m["tp1_hit"] = True
                events.append({"type": "tp1", "ticket": p.ticket, "ok": res.ok})
            if m["tp1_hit"]:
                trail = px - r if long_ else px + r
                better = (trail > p.sl) if long_ else (trail < p.sl or p.sl == 0)
                if better and abs(trail - p.sl) > r * 0.1:
                    self.modify_sl(p.ticket, round(trail, 5), p.tp, "Trailing stop")
        self.db.kv_set("mt5_position_meta", self.meta)
        return events

    def sync(self, days: int = 7) -> dict:
        """Snapshot of open positions and recent closed deals (including manual terminal changes)."""
        if not self.connected:
            return {"positions": [], "deals": []}
        with self._lock:
            positions = self.mt5.positions_get() or []
            now = datetime.now(timezone.utc) + timedelta(hours=24)  # broker server time may run ahead of UTC
            deals = self.mt5.history_deals_get(now - timedelta(days=days), now) or []
        pos_out = [{"ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type == 0 else "SELL", "volume": p.volume,
                    "price_open": p.price_open, "price_current": p.price_current, "sl": p.sl, "tp": p.tp,
                    "profit": p.profit, "magic": p.magic, "comment": p.comment, "time": p.time,
                    "quantpilot": p.magic == self.magic} for p in positions]
        deal_out = [{"ticket": d.ticket, "position_id": d.position_id, "symbol": d.symbol,
                     "type": "BUY" if d.type == 0 else "SELL", "entry": {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}.get(d.entry, "?"),
                     "volume": d.volume, "price": d.price, "profit": d.profit, "time": d.time, "magic": d.magic,
                     "comment": d.comment, "quantpilot": d.magic == self.magic}
                    for d in deals if getattr(d, "symbol", "")]
        deal_out.sort(key=lambda d: d["time"], reverse=True)
        return {"positions": pos_out, "deals": deal_out[:100]}

    def close_all_magic(self) -> list[OrderResult]:
        with self._lock:
            positions = [p for p in (self.mt5.positions_get() or []) if p.magic == self.magic] if self.connected else []
        return [self.close_position(p.ticket, None, "Kill switch") for p in positions]

    def send_test_order(self, instrument: str = "XAUUSD", hold_seconds: float = 3.0) -> dict:
        """Place the minimum lot on a DEMO account, wait, then close it so it appears in Trade and History."""
        if self.account_mode() != "DEMO":
            return {"ok": False, "message": "Test orders are only allowed on a DEMO account."}
        sym = self.sym(instrument)
        with self._lock:
            info = self.mt5.symbol_info(sym)
            tick = self.mt5.symbol_info_tick(sym)
            if info is None or tick is None:
                return {"ok": False, "message": f"No quotes for {sym}. Is the market open?"}
            request = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": info.volume_min,
                       "type": self.mt5.ORDER_TYPE_BUY, "price": tick.ask, "deviation": self.deviation,
                       "magic": self.magic, "comment": "QuantPilot|TEST", "type_time": self.mt5.ORDER_TIME_GTC}
            res, msg = self._check_and_send(request, info)
            code = getattr(res, "retcode", None)
            if res is None or code not in OK_SEND:
                self._emit_log("test_failed", sym, code, None, tick.ask, info.volume_min, msg, request)
                return {"ok": False, "message": msg, "retcode": code}
            ticket = self._find_position_ticket(sym, "TEST")
            self._emit_log("test_open", sym, code, ticket, getattr(res, "price", None), info.volume_min,
                           f"Test order placed · Ticket #{ticket}", request)
        time.sleep(hold_seconds)
        close = self.close_position(ticket, None, "Test close") if ticket else OrderResult(False, "Position not found to close.")
        return {"ok": close.ok, "ticket": ticket, "open_price": getattr(res, "price", None), "close_price": close.price,
                "message": f"Test order #{ticket} opened and {'closed' if close.ok else 'NOT closed: ' + close.message}"}
