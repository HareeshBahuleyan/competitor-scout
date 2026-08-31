from __future__ import annotations

from decimal import Decimal

from competitor_scout.config import Settings


class ConfiguredCostEstimator:
    """Conservative operator-configured preflight estimate, not hosted billing truth."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def __call__(
        self,
        model_alias: str,
        _max_completion_tokens: int,
        enable_web_search: bool,
    ) -> Decimal:
        base = (
            self._settings.estimated_child_request_cost_usd
            if model_alias == self._settings.otari_child_model_alias
            else self._settings.estimated_main_request_cost_usd
        )
        if enable_web_search:
            base += self._settings.estimated_web_search_cost_usd
        return base
