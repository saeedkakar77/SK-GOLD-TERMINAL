"""Hunter: rule-based sweep + displacement detection with exact trade numbers."""
from __future__ import annotations

from ..core.models import AgentResult, AgentStatus
from ..core.strategy import detect_latest
from .base import Agent, CycleContext


class HunterAgent(Agent):
    name = "Hunter"
    role = "Sweep Detector"

    def _run(self, ctx: CycleContext) -> AgentResult:
        setups = detect_latest(ctx.frames["5M"], ctx.instrument, ctx.levels, ctx.services.params)
        ctx.setups = setups
        if not setups:
            ctx.halted = True
            return AgentResult(agent=self.name, status=AgentStatus.SKIP, summary="Scanning: no sweep + displacement on the last close.")
        best = max(setups, key=lambda s: (s.level.strength, s.displacement_ratio))
        ctx.setup = best
        unit = "pips" if best.extension_unit == "pips" else "%"
        return AgentResult(
            agent=self.name, status=AgentStatus.OK, confidence=min(1.0, best.displacement_ratio / 3),
            summary=(f"{best.direction} candidate: {best.level.name} {best.level.price:.2f} swept by "
                     f"{best.extension_depth:g}{unit}, displacement {best.displacement_ratio:.2f}x avg body."),
            data={"setup": best.model_dump(), "candidates": len(setups)},
        )
