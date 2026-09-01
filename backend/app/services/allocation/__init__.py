from app.services.allocation.base import (
    AllocationOutcome, AllocationStrategy, Award, Candidate, SeatPool,
    available_strategies, get_strategy, register,
)
from app.services.allocation.strategies import (  # noqa: F401  (registers strategies)
    ManualAllocation, MeritAllocation, PreferenceOrderAllocation,
)

__all__ = [
    "AllocationStrategy", "Candidate", "SeatPool", "Award", "AllocationOutcome",
    "get_strategy", "available_strategies", "register",
]
