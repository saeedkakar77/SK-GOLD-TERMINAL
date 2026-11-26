"""Scout: market data (5M/15M/4H/Daily), spread and account snapshot from MT5 or Demo."""
from __future__ import annotations

from ..core.indicators import resample, to_frame
from ..core.models import AgentResult, AgentStatus
from .base import Agent, CycleContext


class ScoutAgent(Agent):
    name = "Scout"
    role = "Data"

    def _run(self, ctx: CycleContext) -> AgentResult:
        svc = ctx.services
        source = svc.state.data_source
        if source == "mt5" and svc.mt5.connected:
            candles = svc.mt5.rates(ctx.instrument, "M5", 2000)
            snap = svc.mt5.symbol_snapshot(ctx.instrument) or {}
            ctx.spread_points = float(snap.get("spread_points", 0.0))
            ctx.tick_value, ctx.tick_size = snap.get("tick_value"), snap.get("tick_size")
        else:
            source = "demo"
            candles = svc.feed.candles(ctx.instrument, 2500)
            ctx.spread_points = svc.feed.spread_points(ctx.instrument)
        if len(candles) < 100:
            ctx.halted = True
            return AgentResult(agent=self.name, status=AgentStatus.ERROR, summary=f"Not enough {ctx.instrument} data ({len(candles)} candles).")
        ctx.candles = candles
        df5 = to_frame(candles)
        ctx.frames = {"5M": df5, "15M": resample(df5, "15min"), "4H": resample(df5, "4h"), "D": resample(df5, "1D")}
        ctx.equity = svc.equity()
        last = candles[-1]
        return AgentResult(
            agent=self.name, status=AgentStatus.OK, confidence=1.0,
            summary=f"{ctx.instrument} {last['close']:.2f} · spread {ctx.spread_points:.0f} pts · {len(candles)} bars ({source})",
            data={"source": source, "last": last, "spread_points": ctx.spread_points, "equity": ctx.equity,
                  "bars": {k: len(v) for k, v in ctx.frames.items()}},
        )
