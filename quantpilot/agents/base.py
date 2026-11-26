"""Agent interface shared by all seven QUANT PILOT agents."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from ..core.models import AgentResult, AgentStatus, AnalystDecision, LiquidityLevel, Setup

log = logging.getLogger("quantpilot.agents")


@dataclass
class CycleContext:
    """Everything that flows through one orchestrator cycle for one instrument."""

    instrument: str
    cycle_id: str
    services: Any  # backend.core.orchestrator.Services
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    candles: list[dict] = field(default_factory=list)
    spread_points: float = 0.0
    equity: float = 0.0
    tick_value: Optional[float] = None
    tick_size: Optional[float] = None
    levels: list[LiquidityLevel] = field(default_factory=list)
    setups: list[Setup] = field(default_factory=list)
    setup: Optional[Setup] = None
    decision: Optional[AnalystDecision] = None
    checks: list[dict] = field(default_factory=list)
    volume: float = 0.0
    risk_amount: float = 0.0
    approved: bool = False
    execution: dict = field(default_factory=dict)
    trace: list[AgentResult] = field(default_factory=list)
    halted: bool = False
    outcome: str = "none"  # none | skipped | vetoed | taken | error


class Agent(ABC):
    """Base agent. Subclasses implement ``_run``; ``run`` adds timing and error isolation."""

    name: str = "agent"
    role: str = ""

    def run(self, ctx: CycleContext) -> AgentResult:
        t0 = time.perf_counter()
        try:
            res = self._run(ctx)
        except Exception as exc:  # noqa: BLE001 - one agent failing must not crash the desk
            log.exception("%s failed", self.name)
            res = AgentResult(agent=self.name, status=AgentStatus.ERROR, summary=f"{self.name} error: {type(exc).__name__}")
            ctx.halted = True
            ctx.outcome = "error"
        res.agent = self.name
        res.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        ctx.trace.append(res)
        return res

    @abstractmethod
    def _run(self, ctx: CycleContext) -> AgentResult:
        """Do the agent's work, mutate ctx, return the result."""
