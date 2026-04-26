from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

UseCaseType = Literal[
    "chatbot",
    "code_assistant",
    "multimodal_assistant",
    "analysis",
    "embeddings",
    "unknown",
]
QualityPreference = Literal["quality", "balanced", "budget", "latency", "unknown"]
TrafficPeriod = Literal["day", "month", "unknown"]


@dataclass(slots=True)
class Scenario:
    use_case: UseCaseType = "unknown"
    traffic_period: TrafficPeriod = "unknown"
    requests: int | None = None
    input_tokens_per_request: int | None = None
    output_tokens_per_request: int | None = None
    budget_rub_monthly: float | None = None
    quality_preference: QualityPreference = "unknown"
    needs_image_input: bool = False
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "Scenario") -> "Scenario":
        return Scenario(
            use_case=other.use_case if other.use_case != "unknown" else self.use_case,
            traffic_period=other.traffic_period if other.traffic_period != "unknown" else self.traffic_period,
            requests=other.requests if other.requests is not None else self.requests,
            input_tokens_per_request=(
                other.input_tokens_per_request
                if other.input_tokens_per_request is not None
                else self.input_tokens_per_request
            ),
            output_tokens_per_request=(
                other.output_tokens_per_request
                if other.output_tokens_per_request is not None
                else self.output_tokens_per_request
            ),
            budget_rub_monthly=(
                other.budget_rub_monthly
                if other.budget_rub_monthly is not None
                else self.budget_rub_monthly
            ),
            quality_preference=(
                other.quality_preference
                if other.quality_preference != "unknown"
                else self.quality_preference
            ),
            needs_image_input=other.needs_image_input or self.needs_image_input,
            notes=[*self.notes, *other.notes],
        )

    @property
    def has_minimum_for_costing(self) -> bool:
        has_basic_traffic = (
            self.requests is not None
            and self.input_tokens_per_request is not None
            and self.traffic_period != "unknown"
        )
        if not has_basic_traffic:
            return False
        if self.use_case == "embeddings":
            return True
        return self.output_tokens_per_request is not None

    def requests_per_day(self) -> float | None:
        if self.requests is None:
            return None
        if self.traffic_period == "day":
            return float(self.requests)
        if self.traffic_period == "month":
            return float(self.requests) / 30.0
        return None

    def requests_per_month(self) -> float | None:
        if self.requests is None:
            return None
        if self.traffic_period == "month":
            return float(self.requests)
        if self.traffic_period == "day":
            return float(self.requests) * 30.0
        return None


@dataclass(slots=True)
class ModelPricing:
    input_price_per_1k: float
    output_price_per_1k: float | None
    input_price_per_1k_promo: float | None = None
    output_price_per_1k_promo: float | None = None
    billing_unit_tokens: int = 100

    def effective_input_price(self, today: date, promo_active: bool) -> float:
        _ = today
        if promo_active and self.input_price_per_1k_promo is not None:
            return self.input_price_per_1k_promo
        return self.input_price_per_1k

    def effective_output_price(self, today: date, promo_active: bool) -> float | None:
        _ = today
        if promo_active and self.output_price_per_1k_promo is not None:
            return self.output_price_per_1k_promo
        return self.output_price_per_1k


@dataclass(slots=True)
class ModelInfo:
    name: str
    developer: str
    input_formats: tuple[str, ...]
    output_format: str
    context_k_tokens: int
    size_b_params: float
    pricing: ModelPricing | None = None

    @property
    def is_embedding(self) -> bool:
        return self.output_format.lower() == "embedding"

    @property
    def supports_image_input(self) -> bool:
        return any(fmt.lower() == "image" for fmt in self.input_formats)


@dataclass(slots=True)
class CatalogSnapshot:
    fetched_at: datetime
    models: list[ModelInfo]
    quota_deployments_per_project: int | None
    source_urls: dict[str, str]
    promo_active: bool = False
    promo_note: str | None = None


@dataclass(slots=True)
class CostEstimate:
    input_tokens_monthly: float | None
    output_tokens_monthly: float | None
    monthly_24h_window_rub: float | None
    monthly_isolated_floor_rub: float | None
    input_billed_tokens_monthly_window: float | None
    output_billed_tokens_monthly_window: float | None
    tariff_input_per_1k: float
    tariff_output_per_1k: float | None
    billing_unit_tokens: int


@dataclass(slots=True)
class Recommendation:
    model: ModelInfo
    score: float
    reasons: list[str]
    warnings: list[str]
    estimate: CostEstimate | None = None
