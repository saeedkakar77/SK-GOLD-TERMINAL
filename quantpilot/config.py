"""Central configuration loaded from environment variables (.env).

Secrets (MT5 password, API keys) are read here and never logged or returned
by any API endpoint.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable process settings. Runtime-editable rules live in core.risk.RiskRules."""

    demo_mode: bool = field(default_factory=lambda: _bool("DEMO_MODE", True))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip())
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip())
    analyst_timeout_s: float = field(default_factory=lambda: _float("ANALYST_TIMEOUT_S", 30.0))

    mt5_mode: str = field(default_factory=lambda: os.getenv("MT5_MODE", "demo_only").strip().lower())
    mt5_login: int = field(default_factory=lambda: _int("MT5_LOGIN", 0))
    mt5_password: str = field(default_factory=lambda: os.getenv("MT5_PASSWORD", ""), repr=False)
    mt5_server: str = field(default_factory=lambda: os.getenv("MT5_SERVER", "").strip())
    mt5_path: str = field(default_factory=lambda: os.getenv("MT5_PATH", "").strip().strip('"'))
    mt5_magic: int = field(default_factory=lambda: _int("MT5_MAGIC", 20260101))
    mt5_deviation: int = field(default_factory=lambda: _int("MT5_DEVIATION", 20))

    demo_cycle_seconds: float = field(default_factory=lambda: _float("DEMO_CYCLE_SECONDS", 3.0))
    starting_balance: float = field(default_factory=lambda: _float("PAPER_STARTING_BALANCE", 10000.0))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", str(ROOT_DIR / "backend" / "quantpilot.db")))
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _int("API_PORT", 8765))

    def __repr__(self) -> str:  # never leak secrets
        return (
            f"Settings(demo_mode={self.demo_mode}, model={self.anthropic_model}, "
            f"mt5_mode={self.mt5_mode}, mt5_server={self.mt5_server!r}, api_key_set={bool(self.anthropic_api_key)})"
        )


settings = Settings()

INSTRUMENTS: tuple[str, ...] = ("XAUUSD", "BTCUSD")
CONFIRM_PHRASE = "I UNDERSTAND THE RISK"
