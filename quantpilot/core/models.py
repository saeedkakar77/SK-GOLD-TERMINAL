"""Pydantic models shared across agents, API and persistence."""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentStatus(str, Enum):
    OK = "ok"
    SKIP = "skip"
    VETO = "veto"
    ERROR = "error"


class AgentResult(BaseModel):
    """Common return type of every agent's run(context)."""

    agent: str
    status: AgentStatus
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    latency_ms: float = 0.0


class LiquidityLevel(BaseModel):
    """A price where resting stop-losses (liquidity) are likely to sit."""

    name: str  # e.g. PDH, PDL, ASIA_HIGH, SWING_4H_HIGH, EQH
    price: float
    side: Literal["high", "low"]
    strength: int = 1  # number of touches / confluence


class Setup(BaseModel):
    """A rule-based sweep candidate produced by the Hunter (exact numbers)."""

    signal_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    instrument: str
    direction: Literal["LONG", "SHORT"]
    level: LiquidityLevel
    sweep_time: int
    confirm_time: int
    sweep_extreme: float
    extension_depth: float  # pips for XAU, percent for BTC
    extension_unit: Literal["pips", "pct"]
    displacement_ratio: float  # body / average body
    volume_spike: bool
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_ratio: float
    session: str

    @property
    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)


Bias = Literal["BULLISH_SWEEP_LONG", "BEARISH_SWEEP_SHORT", "NO_TRADE"]


class SweepDetails(BaseModel):
    extension_depth: str
    displacement_quality: str


class TradePlan(BaseModel):
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_ratio: float


class AnalystDecision(BaseModel):
    """Strict schema the Analyst (Claude) must return."""

    instrument: str
    bias: Bias
    confidence_score: int = Field(ge=1, le=10)
    htf_level_targeted: str
    sweep_details: SweepDetails
    trade_plan: TradePlan
    reasoning: str
    invalidation_conditions: list[str] | str

    @field_validator("reasoning")
    @classmethod
    def _max_three_sentences(cls, v: str) -> str:
        sentences = [s for s in v.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if len(sentences) > 3:
            v = ". ".join(s.strip() for s in sentences[:3]) + "."
        return v.strip()

    @model_validator(mode="after")
    def _plan_consistency(self) -> "AnalystDecision":
        if self.bias == "NO_TRADE":
            return self
        p = self.trade_plan
        if self.bias == "BULLISH_SWEEP_LONG" and not (p.stop_loss < p.entry_price < p.take_profit_1):
            raise ValueError("long plan must satisfy SL < entry < TP1")
        if self.bias == "BEARISH_SWEEP_SHORT" and not (p.stop_loss > p.entry_price > p.take_profit_1):
            raise ValueError("short plan must satisfy SL > entry > TP1")
        return self


class Position(BaseModel):
    """A paper or MT5 position as shown in the UI."""

    id: str
    signal_id: str
    instrument: str
    direction: Literal["LONG", "SHORT"]
    volume: float
    initial_volume: float
    entry_price: float
    stop_loss: float
    initial_stop: float
    take_profit_1: float
    take_profit_2: float
    opened_at: float
    status: Literal["open", "closed"] = "open"
    closed_at: Optional[float] = None
    exit_price: Optional[float] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    tp1_hit: bool = False
    breakeven: bool = False
    venue: Literal["paper", "mt5"] = "paper"
    ticket: Optional[int] = None
    close_reason: Optional[str] = None
