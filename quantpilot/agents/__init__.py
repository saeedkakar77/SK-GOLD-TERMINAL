"""The seven cooperating QUANT PILOT agents."""
from .analyst import AnalystAgent
from .cartographer import CartographerAgent
from .chronicler import ChroniclerAgent
from .executioner import ExecutionerAgent
from .guardian import GuardianAgent
from .hunter import HunterAgent
from .scout import ScoutAgent

PIPELINE_ORDER = ["Scout", "Cartographer", "Hunter", "Analyst", "Guardian", "Executioner", "Chronicler"]

__all__ = [
    "ScoutAgent", "CartographerAgent", "HunterAgent", "AnalystAgent", "GuardianAgent",
    "ExecutionerAgent", "ChroniclerAgent", "PIPELINE_ORDER",
]
