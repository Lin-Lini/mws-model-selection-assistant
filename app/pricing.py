from __future__ import annotations

import math
from datetime import date

from app.models import CostEstimate, ModelInfo, Scenario



def _billable_tokens_in_24h_windows(total_requests_per_day: float, tokens_per_request: int, unit: int) -> float:
    if total_requests_per_day <= 0:
        return 0.0
    daily_tokens = total_requests_per_day * tokens_per_request
    return math.floor(daily_tokens / unit) * unit



def _billable_tokens_isolated(total_requests_per_month: float, tokens_per_request: int, unit: int) -> float:
    if total_requests_per_month <= 0:
        return 0.0
    return total_requests_per_month * (math.floor(tokens_per_request / unit) * unit)



def estimate_monthly_cost(
    scenario: Scenario,
    model: ModelInfo,
    *,
    promo_active: bool,
    today: date | None = None,
) -> CostEstimate | None:
    if not scenario.has_minimum_for_costing:
        return None
    today = today or date.today()
    requests_per_day = scenario.requests_per_day()
    requests_per_month = scenario.requests_per_month()
    if requests_per_day is None or requests_per_month is None:
        return None
    pricing = model.pricing
    if pricing is None:
        return None
    unit = pricing.billing_unit_tokens
    input_monthly = requests_per_month * float(scenario.input_tokens_per_request or 0)
    output_monthly = requests_per_month * float(scenario.output_tokens_per_request or 0)

    input_daily_billable = _billable_tokens_in_24h_windows(requests_per_day, scenario.input_tokens_per_request or 0, unit)
    output_daily_billable = _billable_tokens_in_24h_windows(requests_per_day, scenario.output_tokens_per_request or 0, unit)
    input_monthly_window = input_daily_billable * 30
    output_monthly_window = output_daily_billable * 30

    input_monthly_isolated = _billable_tokens_isolated(requests_per_month, scenario.input_tokens_per_request or 0, unit)
    output_monthly_isolated = _billable_tokens_isolated(requests_per_month, scenario.output_tokens_per_request or 0, unit)

    input_tariff = pricing.effective_input_price(today, promo_active=promo_active)
    output_tariff = pricing.effective_output_price(today, promo_active=promo_active)

    window_cost = (input_monthly_window / 1000.0) * input_tariff
    isolated_cost = (input_monthly_isolated / 1000.0) * input_tariff
    if output_tariff is not None:
        window_cost += (output_monthly_window / 1000.0) * output_tariff
        isolated_cost += (output_monthly_isolated / 1000.0) * output_tariff

    return CostEstimate(
        input_tokens_monthly=input_monthly,
        output_tokens_monthly=output_monthly,
        monthly_24h_window_rub=round(window_cost, 4),
        monthly_isolated_floor_rub=round(isolated_cost, 4),
        input_billed_tokens_monthly_window=input_monthly_window,
        output_billed_tokens_monthly_window=output_monthly_window,
        tariff_input_per_1k=input_tariff,
        tariff_output_per_1k=output_tariff,
        billing_unit_tokens=unit,
    )
