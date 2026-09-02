from __future__ import annotations

from decimal import Decimal
from typing import Literal

from competitor_scout.config import Settings

type CostEstimateRole = Literal["main", "child"]


class ConfiguredCostEstimator:
    """Conservative operator-configured preflight estimate, not hosted billing truth."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def __call__(
        self,
        role: CostEstimateRole,
    ) -> Decimal:
        return (
            self._settings.estimated_child_request_cost_usd
            if role == "child"
            else self._settings.estimated_main_request_cost_usd
        )
