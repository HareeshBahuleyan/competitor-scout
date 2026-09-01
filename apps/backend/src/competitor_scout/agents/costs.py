from __future__ import annotations

from decimal import Decimal

from competitor_scout.config import Settings


class ConfiguredCostEstimator:
    """Conservative operator-configured preflight estimate, not hosted billing truth."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def __call__(
        self,
        model: str,
        _max_completion_tokens: int,
        _enable_web_search: bool,
    ) -> Decimal:
        return (
            self._settings.estimated_child_request_cost_usd
            if model == self._settings.otari_child_model
            else self._settings.estimated_main_request_cost_usd
        )
