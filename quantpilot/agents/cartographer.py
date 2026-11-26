"""Cartographer: maps liquidity pools (PDH/PDL, Asian range, 4H swings, equal highs/lows)."""
from __future__ import annotations

from ..core.models import AgentResult, AgentStatus
from ..core.strategy import map_liquidity
from .base import Agent, CycleContext


class CartographerAgent(Agent):
    name = "Cartographer"
    role = "Liquidity Mapper"

    def _run(self, ctx: CycleContext) -> AgentResult:
        df5 = ctx.frames["5M"]
        # map from history that excludes the live sweep window so the sweep cannot redefine its own level
        hist = df5.iloc[-864:-(ctx.services.params.confirm_candles + 1)]
        ctx.levels = map_liquidity(hist, ctx.instrument, ctx.services.params)
        price = float(df5["close"].iloc[-1])
        above = [lv for lv in ctx.levels if lv.price > price]
        below = [lv for lv in ctx.levels if lv.price < price]
        nearest = []
        if above:
            nearest.append(f"{min(above, key=lambda x: x.price).name} {min(above, key=lambda x: x.price).price:.2f} above")
        if below:
            nearest.append(f"{max(below, key=lambda x: x.price).name} {max(below, key=lambda x: x.price).price:.2f} below")
        return AgentResult(
            agent=self.name, status=AgentStatus.OK, confidence=1.0,
            summary=f"{len(ctx.levels)} liquidity pools mapped. " + " · ".join(nearest),
            data={"levels": [lv.model_dump() for lv in ctx.levels]},
        )
