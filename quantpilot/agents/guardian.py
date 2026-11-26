"""Risk Guardian (AEGIS): hard-coded vetoes and automatic lot sizing. Its veto is final."""
from __future__ import annotations

from datetime import datetime, timezone

from ..core.indicators import SPECS
from ..core.models import AgentResult, AgentStatus
from ..core.risk import evaluate
from .base import Agent, CycleContext


class GuardianAgent(Agent):
    name = "Guardian"
    role = "AEGIS Risk"

    def _run(self, ctx: CycleContext) -> AgentResult:
        svc = ctx.services
        setup, decision = ctx.setup, ctx.decision
        assert setup is not None and decision is not None
        plan = decision.trade_plan
        hour = datetime.fromtimestamp(setup.confirm_time, tz=timezone.utc).hour
        spec = SPECS[ctx.instrument]
        if svc.state.data_source == "mt5" and svc.mt5.connected:
            snap = svc.mt5.symbol_snapshot(ctx.instrument)
            if snap:
                spec = spec.__class__(**{**spec.__dict__, "volume_min": snap["volume_min"], "volume_step": snap["volume_step"],
                                         "volume_max": snap["volume_max"], "contract_size": snap["contract_size"]})
        checks, vol, risk_amt = evaluate(
            svc.rules, svc.guardian_state,
            instrument=ctx.instrument, direction=setup.direction, entry=plan.entry_price, stop=plan.stop_loss,
            tp1=plan.take_profit_1, confidence=decision.confidence_score, session=setup.session,
            spread_points=ctx.spread_points, equity=ctx.equity, open_trades=svc.open_trade_count(),
            signal_id=setup.signal_id, level_key=f"{ctx.instrument}:{setup.level.name}", candle_hour_utc=hour,
            analyst_bias=decision.bias, spec=spec, tick_value=ctx.tick_value, tick_size=ctx.tick_size,
            now=svc.clock(),
        )
        ctx.checks = [c.__dict__ for c in checks]
        ctx.volume, ctx.risk_amount = vol, risk_amt
        failed = [c for c in checks if not c.passed]
        svc.guardian_state.processed_ids.add(setup.signal_id)
        if failed:
            ctx.halted = True
            ctx.outcome = "vetoed"
            reasons = "; ".join(f"{c.name}: {c.detail}" for c in failed)
            return AgentResult(agent=self.name, status=AgentStatus.VETO, confidence=0.0,
                               summary=f"VETO: {reasons}", data={"checks": ctx.checks, "volume": vol})
        ctx.approved = True
        svc.guardian_state.recent_signals[f"{ctx.instrument}:{setup.level.name}"] = svc.clock()
        return AgentResult(agent=self.name, status=AgentStatus.OK, confidence=1.0,
                           summary=f"APPROVED: all {len(checks)} checks passed. {vol} lots, risking ${risk_amt:,.2f}.",
                           data={"checks": ctx.checks, "volume": vol, "risk_amount": risk_amt})
