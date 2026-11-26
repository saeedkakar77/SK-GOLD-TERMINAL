"""Analyst: Claude reviews the Hunter's candidate and returns strict JSON (validated by Pydantic).

Claude may only refine or reject the candidate. It can never invent prices: the
entry and stop are pinned to the Hunter's numbers and targets are clamped to the
candidate's range. Without an API key a deterministic rule-based mock is used.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import ValidationError

from ..core.models import AgentResult, AgentStatus, AnalystDecision, Setup, SweepDetails, TradePlan
from .base import Agent, CycleContext

log = logging.getLogger("quantpilot.analyst")

SYSTEM_PROMPT = """You are the Analyst agent in QUANT PILOT, an educational liquidity-sweep trading desk.
A deterministic Hunter agent has detected a candidate stop-hunt reversal. Your job is to judge its quality
and either confirm (optionally refine) it or reject it with NO_TRADE.

Rules:
- You may only refine or reject. Never invent prices: entry_price and stop_loss must equal the candidate's.
  take_profit_1 / take_profit_2 may only be moved closer to entry, never beyond the candidate's TP2.
- bias must match the candidate direction (LONG -> BULLISH_SWEEP_LONG, SHORT -> BEARISH_SWEEP_SHORT) or be NO_TRADE.
- confidence_score is an integer 1-10. Use 7+ only for clean sweeps of meaningful levels with strong displacement
  in an appropriate session.
- reasoning: at most 3 sentences.
- Reply with ONE JSON object only, no markdown, matching exactly this schema:
{"instrument": str, "bias": "BULLISH_SWEEP_LONG"|"BEARISH_SWEEP_SHORT"|"NO_TRADE", "confidence_score": int,
 "htf_level_targeted": str, "sweep_details": {"extension_depth": str, "displacement_quality": str},
 "trade_plan": {"entry_price": float, "stop_loss": float, "take_profit_1": float, "take_profit_2": float,
 "risk_reward_ratio": float}, "reasoning": str, "invalidation_conditions": [str]}"""


def _bias(setup: Setup) -> str:
    return "BULLISH_SWEEP_LONG" if setup.direction == "LONG" else "BEARISH_SWEEP_SHORT"


def _plan(setup: Setup) -> TradePlan:
    return TradePlan(entry_price=setup.entry_price, stop_loss=setup.stop_loss, take_profit_1=setup.take_profit_1,
                     take_profit_2=setup.take_profit_2, risk_reward_ratio=setup.risk_reward_ratio)


def mock_decision(setup: Setup, params_mid: Optional[float] = None) -> AnalystDecision:
    """Deterministic rule-based scoring used when no API key is configured (and in backtests)."""
    score = 4.0
    dq = "strong" if setup.displacement_ratio >= 2.0 else ("moderate" if setup.displacement_ratio >= 1.5 else "weak")
    score += {"strong": 2, "moderate": 1, "weak": 0}[dq]
    if setup.volume_spike:
        score += 1
    if setup.level.strength >= 2 or "+" in setup.level.name:
        score += 1
    session_ok = setup.session in ("LONDON", "NEW_YORK") or setup.instrument == "BTCUSD"
    if session_ok:
        score += 1
    lo, hi = (10, 25) if setup.extension_unit == "pips" else (0.15, 0.40)
    mid = params_mid if params_mid is not None else (lo + hi) / 2
    if abs(setup.extension_depth - mid) <= (hi - lo) * 0.3:
        score += 1
    conf = int(max(1, min(10, round(score))))
    unit = "pips" if setup.extension_unit == "pips" else "%"
    side_word = "sell-side" if setup.direction == "LONG" else "buy-side"
    reasoning = (
        f"Price ran {side_word} liquidity resting at {setup.level.name} ({setup.level.price:.2f}) by {setup.extension_depth:g}{unit} "
        f"and was rejected back inside the range. "
        f"The displacement candle body was {setup.displacement_ratio:.1f}x the average{' with a volume spike' if setup.volume_spike else ''}, "
        f"which suggests trapped breakout traders. "
        f"Targeting 1:{setup.risk_reward_ratio:g} at TP1 with the stop beyond the sweep wick at {setup.stop_loss:.2f}."
    )
    return AnalystDecision(
        instrument=setup.instrument, bias=_bias(setup), confidence_score=conf,  # type: ignore[arg-type]
        htf_level_targeted=f"{setup.level.name} @ {setup.level.price:.2f}",
        sweep_details=SweepDetails(extension_depth=f"{setup.extension_depth:g} {unit}", displacement_quality=dq),
        trade_plan=_plan(setup), reasoning=reasoning,
        invalidation_conditions=[f"5M close back beyond {setup.sweep_extreme:.2f} (sweep extreme)",
                                 "No follow-through within 3 candles", "High-impact news hour"],
    )


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in response")
    return m.group(0)


def clamp_to_candidate(decision: AnalystDecision, setup: Setup) -> tuple[AnalystDecision, list[str]]:
    """Enforce 'refine or reject only': pin entry/SL, keep targets inside the candidate's range."""
    notes: list[str] = []
    if decision.bias == "NO_TRADE":
        return decision, notes
    if decision.bias != _bias(setup):
        notes.append("Analyst bias contradicted the candidate direction: treated as NO_TRADE.")
        decision.bias = "NO_TRADE"
        return decision, notes
    p = decision.trade_plan
    if abs(p.entry_price - setup.entry_price) > 1e-6 or abs(p.stop_loss - setup.stop_loss) > 1e-6:
        notes.append("Entry/SL pinned to Hunter's numbers.")
    p.entry_price, p.stop_loss = setup.entry_price, setup.stop_loss
    sign = 1 if setup.direction == "LONG" else -1
    risk = abs(setup.entry_price - setup.stop_loss)

    def inside(tp: float, fallback: float) -> float:
        dist = (tp - setup.entry_price) * sign
        max_dist = (setup.take_profit_2 - setup.entry_price) * sign
        if dist <= 0 or dist > max_dist + 1e-9:
            notes.append(f"Target {tp} outside candidate range: reset to {fallback}.")
            return fallback
        return tp

    p.take_profit_1 = inside(p.take_profit_1, setup.take_profit_1)
    p.take_profit_2 = inside(p.take_profit_2, setup.take_profit_2)
    if (p.take_profit_2 - p.take_profit_1) * sign < 0:
        p.take_profit_2 = p.take_profit_1
    p.risk_reward_ratio = round(abs(p.take_profit_1 - p.entry_price) / risk, 2) if risk else 0.0
    return decision, notes


class AnalystAgent(Agent):
    name = "Analyst"
    role = "Claude"

    def __init__(self, api_key: str, model: str, timeout_s: float = 30.0) -> None:
        self.model = model
        self.client = None
        if api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=1)

    @property
    def mode(self) -> str:
        return "claude" if self.client else "mock"

    def _prompt(self, ctx: CycleContext, setup: Setup) -> str:
        df = ctx.frames["5M"].tail(12)
        recent = [[int(r.time), round(r.open, 2), round(r.high, 2), round(r.low, 2), round(r.close, 2)] for r in df.itertuples()]
        h4 = ctx.frames["4H"].tail(6)
        trend = "up" if len(h4) > 1 and h4["close"].iloc[-1] > h4["close"].iloc[0] else "down"
        return json.dumps({
            "candidate": setup.model_dump(),
            "context": {"session": setup.session, "spread_points": ctx.spread_points, "h4_trend_last_24h": trend,
                        "nearby_levels": [{"name": lv.name, "price": lv.price, "side": lv.side} for lv in ctx.levels][:12],
                        "last_12_5m_candles_t_o_h_l_c": recent},
        })

    def _ask_claude(self, user: str) -> AnalystDecision:
        messages: list[dict] = [{"role": "user", "content": user}]
        last_err = ""
        for attempt in range(2):  # one retry on invalid JSON
            resp = self.client.messages.create(  # type: ignore[union-attr]
                model=self.model, max_tokens=2048, system=SYSTEM_PROMPT, messages=messages,
                output_config={"effort": "low"},
            )
            if resp.stop_reason == "refusal":
                raise ValueError("model declined")
            text = "".join(b.text for b in resp.content if b.type == "text")
            try:
                return AnalystDecision.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as exc:
                last_err = str(exc)[:400]
                log.warning("Analyst JSON invalid (attempt %d): %s", attempt + 1, last_err)
                messages = messages + [
                    {"role": "assistant", "content": [{"type": "text", "text": text or "{}"}]},
                    {"role": "user", "content": f"That was not valid against the schema: {last_err}. Reply with the corrected JSON object only."},
                ]
        raise ValueError(f"invalid JSON after retry: {last_err}")

    def _run(self, ctx: CycleContext) -> AgentResult:
        setup = ctx.setup
        assert setup is not None
        source = "rule-based mock"
        notes: list[str] = []
        if self.client:
            import anthropic

            try:
                decision = self._ask_claude(self._prompt(ctx, setup))
                source = "Claude"
            except ValueError as exc:
                decision = mock_decision(setup)
                decision.bias = "NO_TRADE"
                decision.reasoning = f"Claude response could not be validated ({exc}); defaulting to NO_TRADE."
                source = "Claude (invalid)"
            except anthropic.RateLimitError:
                decision = mock_decision(setup)
                source = "rule-based fallback"
                ctx.services.toast("warning", "Claude rate-limited", "The Analyst used rule-based scoring for this setup.")
            except anthropic.APITimeoutError:
                decision = mock_decision(setup)
                source = "rule-based fallback"
                ctx.services.toast("warning", "Claude timed out", "The Analyst used rule-based scoring for this setup.")
            except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
                decision = mock_decision(setup)
                source = "rule-based fallback"
                code = getattr(exc, "status_code", "network")
                ctx.services.toast("warning", "Claude unavailable", f"API error ({code}). Rule-based scoring used.")
        else:
            decision = mock_decision(setup)
        decision, notes = clamp_to_candidate(decision, setup)
        ctx.decision = decision
        if decision.bias == "NO_TRADE":
            ctx.halted = True
            ctx.outcome = "skipped"
            return AgentResult(agent=self.name, status=AgentStatus.VETO, confidence=decision.confidence_score / 10,
                               summary=f"NO_TRADE ({source}). {decision.reasoning}",
                               data={"decision": decision.model_dump(), "source": source, "notes": notes})
        return AgentResult(
            agent=self.name, status=AgentStatus.OK, confidence=decision.confidence_score / 10,
            summary=f"{decision.bias} · confidence {decision.confidence_score}/10 ({source}). {decision.reasoning}",
            data={"decision": decision.model_dump(), "source": source, "notes": notes},
        )
