from datetime import date

from app.models import ModelInfo, ModelPricing, Scenario
from app.pricing import estimate_monthly_cost


def test_estimate_monthly_cost() -> None:
    scenario = Scenario(
        use_case="chatbot",
        traffic_period="day",
        requests=100,
        input_tokens_per_request=1200,
        output_tokens_per_request=500,
        budget_rub_monthly=10000,
    )
    model = ModelInfo(
        name="qwen3-32b",
        developer="QWEN",
        input_formats=("Text",),
        output_format="Text",
        context_k_tokens=40,
        size_b_params=32,
        pricing=ModelPricing(
            input_price_per_1k=1.098,
            output_price_per_1k=1.098,
            input_price_per_1k_promo=0.054,
            output_price_per_1k_promo=0.219,
            billing_unit_tokens=100,
        ),
    )
    estimate = estimate_monthly_cost(scenario, model, promo_active=True, today=date(2026, 4, 23))
    assert estimate is not None
    assert estimate.monthly_24h_window_rub is not None
    assert estimate.monthly_24h_window_rub > 0
    assert estimate.billing_unit_tokens == 100
    assert estimate.monthly_24h_window_rub >= estimate.monthly_isolated_floor_rub



def test_estimate_monthly_cost_without_promo_uses_base_tariffs() -> None:
    scenario = Scenario(
        use_case="chatbot",
        traffic_period="day",
        requests=10,
        input_tokens_per_request=1000,
        output_tokens_per_request=1000,
    )
    model = ModelInfo(
        name="qwen3-32b",
        developer="QWEN",
        input_formats=("Text",),
        output_format="Text",
        context_k_tokens=40,
        size_b_params=32,
        pricing=ModelPricing(
            input_price_per_1k=10.0,
            output_price_per_1k=20.0,
            input_price_per_1k_promo=1.0,
            output_price_per_1k_promo=2.0,
            billing_unit_tokens=100,
        ),
    )
    estimate = estimate_monthly_cost(scenario, model, promo_active=False, today=date(2026, 4, 23))
    assert estimate is not None
    assert estimate.tariff_input_per_1k == 10.0
    assert estimate.tariff_output_per_1k == 20.0
