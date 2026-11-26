"""Chronicler: journals every decision with the full agent trace and writes the end-of-day review."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..core.models import AgentResult, AgentStatus
from .base import Agent, CycleContext

log = logging.getLogger("quantpilot.chronicler")


class ChroniclerAgent(Agent):
    name = "Chronicler"
    role = "Journal"

    def _run(self, ctx: CycleContext) -> AgentResult:
        if ctx.setup is None:
            return AgentResult(agent=self.name, status=AgentStatus.SKIP, summary="Nothing to journal this cycle.")
        outcome = ctx.outcome if ctx.outcome != "none" else "skipped"
        trace = [r.model_dump() for r in ctx.trace]
        summary = next((r.summary for r in reversed(ctx.trace) if r.status in (AgentStatus.VETO, AgentStatus.ERROR)), None)
        if outcome == "taken":
            summary = next((r.summary for r in ctx.trace if r.agent == "Executioner"), "Trade taken")
        row_id = ctx.services.db.log_decision(ctx.instrument, ctx.setup.signal_id, outcome, summary or outcome, trace)
        return AgentResult(agent=self.name, status=AgentStatus.OK, confidence=1.0,
                           summary=f"Journaled #{row_id}: {outcome.upper()} · {ctx.setup.signal_id}",
                           data={"journal_id": row_id, "outcome": outcome})


def build_daily_review(decisions: list[dict], trades: list[dict], client=None, model: str = "") -> str:
    """AI end-of-day review. Uses Claude when available, otherwise a deterministic summary."""
    taken = [d for d in decisions if d["outcome"] == "taken"]
    vetoed = [d for d in decisions if d["outcome"] == "vetoed"]
    skipped = [d for d in decisions if d["outcome"] == "skipped"]
    pnl = sum(t.get("pnl") or 0 for t in trades)
    wins = [t for t in trades if (t.get("pnl") or 0) > 0]
    veto_reasons: dict[str, int] = {}
    for d in vetoed:
        for part in (d.get("summary") or "").replace("VETO:", "").split(";"):
            key = part.split(":")[0].strip()
            if key:
                veto_reasons[key] = veto_reasons.get(key, 0) + 1
    top_veto = max(veto_reasons, key=veto_reasons.get) if veto_reasons else None
    stats = (f"{len(decisions)} decisions: {len(taken)} taken, {len(vetoed)} vetoed, {len(skipped)} skipped. "
             f"{len(trades)} trades closed, {len(wins)} winners, net P/L ${pnl:,.2f}.")
    if client is not None:
        try:
            resp = client.messages.create(
                model=model, max_tokens=1024, output_config={"effort": "low"},
                system="You are the Chronicler of an educational trading journal. Write a calm, factual end-of-day review "
                       "in 4-6 sentences: what happened, what the risk guardian protected against, one process lesson. "
                       "Never promise profits.",
                messages=[{"role": "user", "content": f"Stats: {stats} Most common veto: {top_veto}. "
                                                      f"Sample decisions: {[d.get('summary') for d in decisions[-8:]]}"}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001 - review falls back to deterministic text
            log.warning("AI review failed: %s", type(exc).__name__)
    lesson = ("The Guardian's most frequent veto was "
              f"'{top_veto}', a reminder that patience is part of the edge." if top_veto else
              "No vetoes today: keep validating that setups meet every rule rather than assuming they will.")
    tone = "a green day" if pnl > 0 else ("a flat day" if pnl == 0 else "a red day, which is a normal part of any edge")
    return (f"{datetime.now(timezone.utc):%d %b %Y} review: {stats} Overall it was {tone}. {lesson} "
            "Process over outcome: every trade risked a fixed fraction and every stop was set before entry.")
