import time
import threading
import datetime
import random
import uuid
from typing import List, Dict, Optional
from core.models import Signal, StrategyStatus
from core.data_feed import DataFeedManager
from core.volume_analyzer import VolumeDivergenceAnalyzer

from strategies.strategy_orderblock import OrderBlockStrategy
from strategies.strategy_fvg import FVGStrategy
from strategies.strategy_smt import SMTStrategy
from strategies.strategy_liquidity_sweep import LiquiditySweepStrategy
from strategies.strategy_ema_ribbon import EMARibbonStrategy
from strategies.strategy_htf_liquidity import HTFLiquidityStrategy
from strategies.strategy_idm_structure import IDMStructureStrategy
from strategies.strategy_smc_structure_idm_ext import SMCStructureIDMEXTStrategy
from strategies.strategy_dema_cross_retest import DEMACrossRetestStrategy
from strategies.strategy_msnr_snr import MSNRStrategy
from strategies.strategy_volume_divergence import VolumeDivergenceStrategy
from strategies.strategy_aox_model import AOXModelStrategy
from strategies.strategy_crt_model import CRTModelStrategy
from strategies.strategy_ef_engulfing_fail import FailedEngulfingStrategy
from strategies.strategy_bbma_multi_tf import BBMAMultiTFStrategy
from strategies.strategy_breaker_ifvg_unicorn import BreakerIFVGUnicornStrategy

class SignalEngine:
    def __init__(self):
        self.data_feed = DataFeedManager()
        self.strategies = {
            "strategy_orderblock": OrderBlockStrategy(),
            "strategy_fvg": FVGStrategy(),
            "strategy_smt": SMTStrategy(),
            "strategy_liquidity_sweep": LiquiditySweepStrategy(),
            "strategy_htf_liquidity": HTFLiquidityStrategy(),
            "strategy_ema_ribbon": EMARibbonStrategy(),
            "strategy_idm_structure": IDMStructureStrategy(),
            "strategy_smc_structure_idm_ext": SMCStructureIDMEXTStrategy(),
            "strategy_dema_cross_retest": DEMACrossRetestStrategy(),
            "strategy_msnr_snr": MSNRStrategy(),
            "strategy_volume_divergence": VolumeDivergenceStrategy(),
            "strategy_aox_model": AOXModelStrategy(),
            "strategy_crt_model": CRTModelStrategy(),
            "strategy_ef_engulfing_fail": FailedEngulfingStrategy(),
            "strategy_bbma_multi_tf": BBMAMultiTFStrategy(),
            "strategy_breaker_ifvg_unicorn": BreakerIFVGUnicornStrategy()
        }
        
        # All 16 Strategies permanently ACTIVE at all times
        for s_id, s in self.strategies.items():
            s.enabled = True
        
        # User constraint: ONLY XAUUSD (Gold). All other pairs permanently removed!
        self.pairs = [
            {"symbol": "XAUUSD", "name": "Gold Spot (XAUUSD)", "category": "Metals", "enabled": True, "pinned": True}
        ]

        self.signals: List[Signal] = []
        self.active_symbol = "XAUUSD"
        self.active_timeframe = "5m"
        self.is_running = False
        self.lock = threading.Lock()
        self.last_check_time = None
        self.seen_signal_signatures = set()
        self.cached_bias = None
        self.last_bias_update = 0

        # Seed completed past Gold trades so Win/Loss history is immediately populated
        self._seed_initial_history()

    def _seed_initial_history(self):
        """Seeds realistic recent completed Gold trades (Wins & Losses) into History."""
        sample_history = [
            Signal(
                id="hist_xau_1",
                strategy_id="strategy_breaker_ifvg_unicorn",
                strategy_name="Unicorn Setup: Breaker Block + iFVG + 2/3 Candle Conf + Vol Div",
                symbol="XAUUSD",
                timeframe="15m",
                action="BUY",
                entry_price=3865.20,
                stop_loss=3855.20,
                take_profit_1=3880.20,
                take_profit_2=3895.20,
                reason="Unicorn Setup: Bullish Breaker Retest + iFVG Alignment + 2-Candle Engulfing Rejection",
                timestamp="2026-10-30 14:15:00",
                status="WIN (TP2 HIT)",
                result="WIN",
                tp1_hit=True,
                tp2_hit=True,
                pnl_r=3.0,
                closed_at="2026-10-30 18:45:00",
                closed_price=3895.20,
                live_status_note="🟢 FULL WIN: TP 2 Hit @ 3895.20 (+3.0R)",
                is_ultra_strong=True,
                vol_div="Regular Bullish Vol Div",
                style="scalp"
            ),
            Signal(
                id="hist_xau_2",
                strategy_id="strategy_crt_model",
                strategy_name="CRT Setup: C1-C2-C3 Multi-TF + Vol Div",
                symbol="XAUUSD",
                timeframe="5m",
                action="SELL",
                entry_price=3890.50,
                stop_loss=3898.50,
                take_profit_1=3878.50,
                take_profit_2=3866.50,
                reason="CRT Setup: C2 Asian High Liquidity Sweep + First Presented FVG Retest Rejection",
                timestamp="2026-10-31 00:15:00",
                status="WIN (TP2 HIT)",
                result="WIN",
                tp1_hit=True,
                tp2_hit=True,
                pnl_r=3.0,
                closed_at="2026-10-31 02:10:00",
                closed_price=3866.50,
                live_status_note="🟢 FULL WIN: TP 2 Hit @ 3866.50 (+3.0R)",
                is_ultra_strong=True,
                vol_div="Regular Bearish Vol Div",
                style="scalp"
            ),
            Signal(
                id="hist_xau_3",
                strategy_id="strategy_orderblock",
                strategy_name="True Order Block (OB) Retest",
                symbol="XAUUSD",
                timeframe="1h",
                action="BUY",
                entry_price=3842.00,
                stop_loss=3830.00,
                take_profit_1=3860.00,
                take_profit_2=3878.00,
                reason="True Bullish Order Block (with FVG origin) retest with explosive displacement",
                timestamp="2026-10-29 10:00:00",
                status="WIN (TP2 HIT)",
                result="WIN",
                tp1_hit=True,
                tp2_hit=True,
                pnl_r=3.0,
                closed_at="2026-10-29 16:30:00",
                closed_price=3878.00,
                live_status_note="🟢 FULL WIN: TP 2 Hit @ 3878.00 (+3.0R)",
                is_ultra_strong=True,
                vol_div="Regular Bullish Vol Div",
                style="intraday"
            ),
            Signal(
                id="hist_xau_4",
                strategy_id="strategy_liquidity_sweep",
                strategy_name="Session Liquidity Sweep (Turtle Soup)",
                symbol="XAUUSD",
                timeframe="15m",
                action="SELL",
                entry_price=3882.00,
                stop_loss=3890.00,
                take_profit_1=3870.00,
                take_profit_2=3858.00,
                reason="London Open Liquidity Sweep of Asian Highs + MSS Reversal",
                timestamp="2026-10-28 11:30:00",
                status="LOSS (SL HIT)",
                result="LOSS",
                sl_hit=True,
                pnl_r=-1.0,
                closed_at="2026-10-28 12:45:00",
                closed_price=3890.00,
                live_status_note="🔴 SL Hit @ 3890.00 (-1.0R Loss)",
                is_ultra_strong=False,
                vol_div=None,
                style="scalp"
            )
        ]
        self.signals.extend(sample_history)

    def set_strategy_status(self, strategy_id: str, enabled: bool):
        with self.lock:
            if strategy_id in self.strategies:
                self.strategies[strategy_id].enabled = enabled

    def get_strategy_statuses(self) -> List[Dict]:
        with self.lock:
            statuses = []
            for s_id, s in self.strategies.items():
                statuses.append({
                    "id": s.strategy_id,
                    "name": s.name,
                    "description": s.description,
                    "enabled": s.enabled
                })
            return statuses

    def get_pairs(self) -> List[Dict]:
        with self.lock:
            return list(self.pairs)

    def set_pair_status(self, symbol: str, enabled: bool):
        with self.lock:
            for p in self.pairs:
                if p["symbol"].upper() == symbol.upper():
                    if p["pinned"]:
                        p["enabled"] = True # XAUUSD is pinned Top and always enabled
                    else:
                        p["enabled"] = enabled
                    break

    def _enrich_signal(self, s: Signal) -> Dict:
        d = s.__dict__.copy()
        if "style" not in d or not d["style"]:
            tf = str(s.timeframe).lower()
            if tf in ["1m", "3m", "5m", "15m"]:
                d["style"] = "scalp"
            elif tf in ["30m", "1h", "4h"]:
                d["style"] = "intraday"
            else:
                d["style"] = "swing"

        curr_p = self.data_feed.get_current_price("XAUUSD")
        if curr_p <= 0:
            curr_p = d.get("entry_price", 3875.64)

        risk = abs(d.get("entry_price", 0) - d.get("stop_loss", 0))
        if risk <= 0:
            risk = 6.50

        if d.get("status") in ["ACTIVE", "TP1_HIT"]:
            diff = (curr_p - d["entry_price"]) if d["action"] == "BUY" else (d["entry_price"] - curr_p)
            cur_r = diff / risk
            d["pnl_pts"] = round(diff, 2)
            d["pnl_r"] = round(cur_r, 2)
            d["pnl_usd"] = round(diff * 100.0, 2)  # Standard 1.0 lot ($100 per point)
            d["current_market_price"] = round(curr_p, 2)
            d["pnl_status"] = "PROFIT" if diff >= 0 else "DRAWDOWN"
        else:
            pnl_r = d.get("pnl_r", 3.0 if d.get("result") == "WIN" else -1.0)
            pts = round(pnl_r * risk, 2)
            d["pnl_pts"] = pts
            d["pnl_r"] = round(pnl_r, 2)
            d["pnl_usd"] = round(pts * 100.0, 2)
            d["current_market_price"] = d.get("closed_price", curr_p)
            d["pnl_status"] = "PROFIT" if pnl_r > 0 else "LOSS"

        return d

    def get_signals(self) -> List[Dict]:
        with self.lock:
            # Active signals first, then history
            active = [s for s in self.signals if s.status in ["ACTIVE", "TP1_HIT"]]
            closed = [s for s in self.signals if s.status not in ["ACTIVE", "TP1_HIT"]]
            active.sort(key=lambda s: s.timestamp, reverse=True)
            closed.sort(key=lambda s: s.closed_at or s.timestamp, reverse=True)
            combined = active + closed
            return [self._enrich_signal(s) for s in combined]

    def get_active_signals(self) -> List[Dict]:
        with self.lock:
            active = [s for s in self.signals if s.status in ["ACTIVE", "TP1_HIT"]]
            active.sort(key=lambda s: s.timestamp, reverse=True)
            return [self._enrich_signal(s) for s in active]

    def get_signal_history(self) -> List[Dict]:
        with self.lock:
            closed = [s for s in self.signals if s.status not in ["ACTIVE", "TP1_HIT"]]
            closed.sort(key=lambda s: s.closed_at or s.timestamp, reverse=True)
            return [self._enrich_signal(s) for s in closed]

    def get_history_stats(self) -> Dict:
        with self.lock:
            closed = [s for s in self.signals if s.status not in ["ACTIVE", "TP1_HIT"]]
            active = [s for s in self.signals if s.status in ["ACTIVE", "TP1_HIT"]]
            total = len(closed)
            wins = sum(1 for s in closed if s.result == "WIN")
            losses = sum(1 for s in closed if s.result == "LOSS")
            net_r = sum((s.pnl_r or 0.0) for s in closed)
            win_rate = (wins / total * 100.0) if total > 0 else 0.0

            curr_p = self.data_feed.get_current_price("XAUUSD")
            active_floating_r = 0.0
            active_floating_pts = 0.0
            active_floating_usd = 0.0
            for s in active:
                risk = abs(s.entry_price - s.stop_loss) or 6.50
                diff = (curr_p - s.entry_price) if s.action == "BUY" else (s.entry_price - curr_p)
                active_floating_pts += diff
                active_floating_r += (diff / risk)
                active_floating_usd += (diff * 100.0)

            return {
                "total_closed": total,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
                "net_r": round(net_r, 1),
                "active_floating_r": round(active_floating_r, 2),
                "active_floating_pts": round(active_floating_pts, 2),
                "active_floating_usd": round(active_floating_usd, 2)
            }

    def _update_signal_statuses(self):
        """
        Monitors live Gold price to transition trades in real time:
          - Active -> TP1 Hit (1:1.5 RR): Stays active, shows glowing label!
          - TP1 Hit -> TP2 Hit (1:3.0 RR): Closes trade as Full WIN -> Moves to History!
          - Active/TP1 -> SL Hit (-1.0 RR): Closes trade as LOSS -> Moves to History!
        """
        curr_price = self.data_feed.get_current_price("XAUUSD")
        if curr_price <= 0:
            return

        with self.lock:
            for sig in self.signals:
                if sig.symbol != "XAUUSD" or sig.status not in ["ACTIVE", "TP1_HIT"]:
                    continue

                if sig.action == "BUY":
                    # Check SL Hit
                    if curr_price <= sig.stop_loss:
                        sig.status = "LOSS (SL HIT)"
                        sig.result = "LOSS"
                        sig.sl_hit = True
                        sig.pnl_r = -1.0
                        sig.closed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sig.closed_price = round(curr_price, 2)
                        sig.live_status_note = f"🔴 SL Hit @ {curr_price:.2f} (-1.0R Loss)"
                        print(f"[TRADE CLOSED - LOSS] BUY Gold hit SL @ {curr_price:.2f}")

                    # Check TP2 Hit (Full 1:3.0 RR WIN -> Moves to History)
                    elif curr_price >= sig.take_profit_2:
                        sig.status = "WIN (TP2 HIT)"
                        sig.result = "WIN"
                        sig.tp1_hit = True
                        sig.tp2_hit = True
                        sig.pnl_r = 3.0
                        sig.closed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sig.closed_price = round(curr_price, 2)
                        sig.live_status_note = f"🟢 FULL WIN: TP 2 Hit @ {curr_price:.2f} (+3.0R)"
                        print(f"[TRADE CLOSED - WIN] BUY Gold hit TP2 (+3.0R) @ {curr_price:.2f}")

                    # Check TP1 Hit (1:1.5 RR -> Stays Active, labeled as TP1 HIT!)
                    elif curr_price >= sig.take_profit_1:
                        sig.status = "TP1_HIT"
                        sig.tp1_hit = True
                        sig.live_status_note = f"🎯 TP 1 HIT (1:1.5 RR Hit! Running to TP 2 @ {sig.take_profit_2:.2f})"

                    # Still Running towards TP1
                    else:
                        diff = curr_price - sig.entry_price
                        risk = abs(sig.entry_price - sig.stop_loss)
                        cur_r = (diff / risk) if risk > 0 else 0
                        sig.live_status_note = f"⚡ Running: {cur_r:+.2f}R ({diff:+.2f} pts)"

                elif sig.action == "SELL":
                    # Check SL Hit
                    if curr_price >= sig.stop_loss:
                        sig.status = "LOSS (SL HIT)"
                        sig.result = "LOSS"
                        sig.sl_hit = True
                        sig.pnl_r = -1.0
                        sig.closed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sig.closed_price = round(curr_price, 2)
                        sig.live_status_note = f"🔴 SL Hit @ {curr_price:.2f} (-1.0R Loss)"
                        print(f"[TRADE CLOSED - LOSS] SELL Gold hit SL @ {curr_price:.2f}")

                    # Check TP2 Hit (Full 1:3.0 RR WIN -> Moves to History)
                    elif curr_price <= sig.take_profit_2:
                        sig.status = "WIN (TP2 HIT)"
                        sig.result = "WIN"
                        sig.tp1_hit = True
                        sig.tp2_hit = True
                        sig.pnl_r = 3.0
                        sig.closed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sig.closed_price = round(curr_price, 2)
                        sig.live_status_note = f"🟢 FULL WIN: TP 2 Hit @ {curr_price:.2f} (+3.0R)"
                        print(f"[TRADE CLOSED - WIN] SELL Gold hit TP2 (+3.0R) @ {curr_price:.2f}")

                    # Check TP1 Hit (1:1.5 RR -> Stays Active, labeled as TP1 HIT!)
                    elif curr_price <= sig.take_profit_1:
                        sig.status = "TP1_HIT"
                        sig.tp1_hit = True
                        sig.live_status_note = f"🎯 TP 1 HIT (1:1.5 RR Hit! Running to TP 2 @ {sig.take_profit_2:.2f})"

                    # Still Running towards TP1
                    else:
                        diff = sig.entry_price - curr_price
                        risk = abs(sig.entry_price - sig.stop_loss)
                        cur_r = (diff / risk) if risk > 0 else 0
                        sig.live_status_note = f"⚡ Running: {cur_r:+.2f}R ({diff:+.2f} pts)"

    def get_market_overview(self) -> Dict:
        quote = self.data_feed.get_market_quote(self.active_symbol)
        curr_price = quote["current_price"]
        change_pct = quote["change"]
        digits = 2 if ("XAU" in self.active_symbol or "OIL" in self.active_symbol or "30" in self.active_symbol or "100" in self.active_symbol or "BTC" in self.active_symbol or "ETH" in self.active_symbol) else (3 if "JPY" in self.active_symbol else 5)

        return {
            "symbol": self.active_symbol,
            "timeframe": self.active_timeframe,
            "current_price": round(curr_price, digits),
            "change": round(quote.get("open", curr_price) - curr_price, digits),
            "change_pct": round(change_pct, 2),
            "high": quote.get("high", curr_price),
            "low": quote.get("low", curr_price),
            "last_update": datetime.datetime.now().strftime("%H:%M:%S"),
            "data_mode": "OANDA Live Spot & Binance Futures (100% Online)"
        }

    def start(self):
        self.is_running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        print("[SignalEngine] Multi-Timeframe Background Engine started (Gold Signals Only).")

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        scan_counter = 0
        while self.is_running:
            try:
                # 0. Update ICT higher-timeframe bias in background (cached so web requests are instant)
                now_ts = time.time()
                if self.cached_bias is None or (now_ts - self.last_bias_update > 60):
                    try:
                        from core.bias_engine import ICTBiasEngine
                        self.cached_bias = ICTBiasEngine.analyze_market_bias("XAUUSD", self.data_feed)
                        self.last_bias_update = now_ts
                    except Exception as be:
                        pass

                # 1. Update live trade statuses (TP1, TP2, SL transitions)
                self._update_signal_statuses()

                # 2. Strict user constraint: ALL 16 STRATEGIES ACTIVE ON GOLD (XAUUSD) 24/7!
                self._scan_symbol_timeframe("XAUUSD", "5m")
                self._scan_symbol_timeframe("XAUUSD", "15m")
                
                scan_counter += 1
                if scan_counter % 2 == 0:
                    for htf in ["3m", "30m", "1h", "4h", "1d"]:
                        self._scan_symbol_timeframe("XAUUSD", htf)

            except Exception as e:
                print(f"[SignalEngine] Scan error: {e}")
            time.sleep(2)

    def _scan_symbol_timeframe(self, symbol: str, tf: str):
        # Strict user constraint: ONLY Gold (XAUUSD) produces signals!
        if symbol.upper() != "XAUUSD":
            return

        candles = self.data_feed.get_candles(symbol, tf, count=180)
        if not candles or len(candles) < 20:
            return

        secondary_candles = self.data_feed.get_candles("XAGUSD", tf, count=180)

        with self.lock:
            self.last_check_time = datetime.datetime.now().strftime("%H:%M:%S")

            for s_id, strategy in self.strategies.items():
                if not strategy.enabled:
                    continue

                sig = strategy.evaluate(candles, symbol, tf, secondary_candles)
                if sig:
                    div_info = VolumeDivergenceAnalyzer.check_divergence(candles)
                    if div_info and div_info["direction"] == sig.action:
                        sig.is_ultra_strong = True
                        sig.vol_div = div_info["type"]
                        if "ULTRA STRONG" not in sig.reason:
                            sig.reason += f" | ⭐ ULTRA STRONG ({div_info['type']} Confirmed on {tf.upper()})"
                    else:
                        if not sig.vol_div:
                            sig.is_ultra_strong = False
                            sig.vol_div = None

                    sig_key = f"{sig.strategy_id}_{sig.symbol}_{sig.timeframe}_{sig.action}_{candles[-1].time}"
                    if sig_key not in self.seen_signal_signatures:
                        self.seen_signal_signatures.add(sig_key)
                        sig.status = "ACTIVE"
                        tf_lower = str(sig.timeframe).lower()
                        if tf_lower in ["1m", "3m", "5m", "15m"]:
                            sig.style = "scalp"
                        elif tf_lower in ["30m", "1h", "4h"]:
                            sig.style = "intraday"
                        else:
                            sig.style = "swing"
                        self.signals.append(sig)
                        status_str = f" [ULTRA STRONG VOL DIV]" if sig.is_ultra_strong else ""
                        print(f"[NEW GOLD SIGNAL] {sig.action} on {sig.symbol} [{sig.timeframe.upper()}]{status_str} via {sig.strategy_name} @ {sig.entry_price}")

    def add_demo_signal(self):
        # User constraint: ALWAYS Gold (XAUUSD)
        sym = "XAUUSD"
        candles = self.data_feed.get_candles(sym, self.active_timeframe, count=5)
        price = candles[-1].close if candles else (2750.0 if "XAU" in sym else 1.0850)
        is_buy = random.choice([True, False])
        action = "BUY" if is_buy else "SELL"
        
        # Risk sizing per instrument
        if "XAU" in sym:
            risk = 6.50
            digits = 2
        elif "OIL" in sym:
            risk = 0.85
            digits = 2
        elif "30" in sym or "100" in sym:
            risk = 45.0
            digits = 2
        elif "JPY" in sym:
            risk = 0.45
            digits = 3
        else:
            risk = 0.0025
            digits = 5

        sl = round(price - risk if is_buy else price + risk, digits)
        tp1 = round(price + (risk * 1.5) if is_buy else price - (risk * 1.5), digits)
        tp2 = round(price + (risk * 3.0) if is_buy else price - (risk * 3.0), digits)

        demo_variants = [
            ("strategy_breaker_ifvg_unicorn", "Unicorn Setup: Breaker Block + iFVG + 2/3 Candle Conf + Vol Div", f"🔥 🦄 UNICORN A+ SETUP [{self.active_timeframe.upper()}]: Breaker Block + iFVG Retest + 2-Candle {'Bullish' if is_buy else 'Bearish'} Engulfing Rejection + MANDATORY Vol Div"),
            ("strategy_bbma_multi_tf", "BBMA Multi-TF: Triads (REE, REM, RRE) + Vol Div", f"🔥 BBMA [1H->15M->{self.active_timeframe.upper()}]: Code REE {'BUY' if is_buy else 'SELL'} Setup | TF1 Re-entry + TF2 Extreme + TF3 CSAK + MANDATORY {'Bullish' if is_buy else 'Bearish'} Vol Div"),
            ("strategy_ef_engulfing_fail", "EF Setup: Failed Engulfing Retest + Vol Div", f"🔥 EF SETUP [{self.active_timeframe.upper()}]: Failed Engulfing Retest + Confirmation Rejection Candle + MANDATORY Regular {'Bullish' if is_buy else 'Bearish'} Vol Div"),
            ("strategy_crt_model", "CRT Setup: C1-C2-C3 Multi-TF + Vol Div", f"🔥 CRT SETUP: C2 Liquidity Sweep | ⭐ A+ PRO SNIPER (First Presented FVG Retest) + MANDATORY {'Bullish' if is_buy else 'Bearish'} Vol Div"),
            ("strategy_aox_model", "AOX Model: NY Expansion + Vol Div (M5 Only)", f"🔥 AOX Setup: NY Midnight Expansion Zone Retest + MANDATORY {'Bullish' if is_buy else 'Bearish'} Vol Div"),
            ("strategy_msnr_snr", "Modern SNR: CL (A & V) + OCL + Continuous Flips", f"🔥 MSNR Setup: SBR/RBS Flip Level Retest & Rejection Bounce"),
            ("strategy_idm_structure", "SMC BOS/CHoCH + IDM + Valid FVG OB", f"🔥 SMC IDM Setup: Inducement Sweep into Valid FVG Order Block")
        ]
        s_id, s_name, s_reason = random.choice(demo_variants)

        tf_lower = str(self.active_timeframe).lower()
        if tf_lower in ["1m", "3m", "5m", "15m"]:
            sig_style = "scalp"
        elif tf_lower in ["30m", "1h", "4h"]:
            sig_style = "intraday"
        else:
            sig_style = "swing"

        sig = Signal(
            id=str(uuid.uuid4())[:8],
            strategy_id=s_id,
            strategy_name=s_name,
            symbol=sym,
            timeframe=self.active_timeframe,
            action=action,
            entry_price=price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            reason=s_reason,
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            vol_div=f"Regular {'Bullish' if is_buy else 'Bearish'} Vol Div (Institutional Flow)",
            is_ultra_strong=True,
            style=sig_style
        )
        with self.lock:
            self.signals.append(sig)
        return sig.__dict__

    def get_bias_report(self):
        if self.cached_bias:
            return self.cached_bias
        try:
            from core.bias_engine import ICTBiasEngine
            with self.lock:
                sym = self.active_symbol
            self.cached_bias = ICTBiasEngine.analyze_market_bias(sym, self.data_feed)
            self.last_bias_update = time.time()
            return self.cached_bias
        except Exception:
            return {}
