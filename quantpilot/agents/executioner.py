"""Executioner: sends Guardian-approved orders to the paper engine (default) or the MT5 bridge."""
from __future__ import annotations

from ..core.models import AgentResult, AgentStatus
from .base import Agent, CycleContext


class ExecutionerAgent(Agent):
    name = "Executioner"
    role = "Execution"

    def _run(self, ctx: CycleContext) -> AgentResult:
        svc = ctx.services
        # Hard gate: nothing executes without Guardian approval, regardless of Analyst output.
        if not ctx.approved or ctx.setup is None or ctx.decision is None:
            ctx.halted = True
            return AgentResult(agent=self.name, status=AgentStatus.SKIP, summary="Not approved by Guardian: nothing sent.")
        setup, plan = ctx.setup, ctx.decision.trade_plan
        if svc.state.execution == "mt5":
            if not svc.mt5.is_ready():
                ctx.outcome = "error"
                return AgentResult(agent=self.name, status=AgentStatus.ERROR,
                                   summary="MT5 not ready: order NOT sent. Check the MT5 status card for the fix.")
            res = svc.mt5.place_order(signal_id=setup.signal_id, instrument=ctx.instrument, direction=setup.direction,
                                      volume=ctx.volume, sl=plan.stop_loss, tp1=plan.take_profit_1, tp2=plan.take_profit_2,
                                      cooldown_s=60.0)
            ctx.execution = {"venue": "mt5", **res.to_dict()}
            if not res.ok:
                ctx.outcome = "vetoed" if res.duplicate else "error"
                return AgentResult(agent=self.name, status=AgentStatus.ERROR if not res.duplicate else AgentStatus.SKIP,
                                   summary=f"MT5: {res.message}", data=ctx.execution)
            ctx.outcome = "taken"
            svc.on_trade_placed(ctx, venue="mt5", ticket=res.ticket, price=res.price, volume=res.volume)
            return AgentResult(agent=self.name, status=AgentStatus.OK, confidence=1.0,
                               summary=f"{res.message} · {setup.direction} {res.volume} {res.symbol} @ {res.price}",
                               data=ctx.execution)
        pos = svc.paper.open(signal_id=setup.signal_id, instrument=ctx.instrument, direction=setup.direction,
                             volume=ctx.volume, price=plan.entry_price, sl=plan.stop_loss, tp1=plan.take_profit_1,
                             tp2=plan.take_profit_2, ts=setup.confirm_time)
        ctx.execution = {"venue": "paper", "position": pos.model_dump()}
        ctx.outcome = "taken"
        svc.on_trade_placed(ctx, venue="paper", ticket=None, price=pos.entry_price, volume=pos.volume)
        return AgentResult(agent=self.name, status=AgentStatus.OK, confidence=1.0,
                           summary=f"Paper {setup.direction} {pos.volume} {ctx.instrument} @ {pos.entry_price} · SL {pos.stop_loss} · TP1 {pos.take_profit_1} · TP2 {pos.take_profit_2}",
                           data=ctx.execution)
