from __future__ import annotations

from datetime import datetime, timezone

from app.models import CatalogSnapshot, CostEstimate, ModelInfo, ModelPricing, Recommendation, Scenario


def scenario_to_state(scenario: Scenario) -> dict:
    return {
        'use_case': scenario.use_case,
        'traffic_period': scenario.traffic_period,
        'requests': scenario.requests,
        'input_tokens_per_request': scenario.input_tokens_per_request,
        'output_tokens_per_request': scenario.output_tokens_per_request,
        'budget_rub_monthly': scenario.budget_rub_monthly,
        'quality_preference': scenario.quality_preference,
        'needs_image_input': scenario.needs_image_input,
        'notes': list(scenario.notes),
    }



def scenario_from_state(data: dict | None) -> Scenario:
    if not data:
        return Scenario()
    return Scenario(
        use_case=data.get('use_case', 'unknown'),
        traffic_period=data.get('traffic_period', 'unknown'),
        requests=data.get('requests'),
        input_tokens_per_request=data.get('input_tokens_per_request'),
        output_tokens_per_request=data.get('output_tokens_per_request'),
        budget_rub_monthly=data.get('budget_rub_monthly'),
        quality_preference=data.get('quality_preference', 'unknown'),
        needs_image_input=bool(data.get('needs_image_input', False)),
        notes=list(data.get('notes', [])),
    )



def snapshot_meta_to_state(snapshot: CatalogSnapshot) -> dict:
    return {
        'fetched_at': snapshot.fetched_at.isoformat(),
        'quota_deployments_per_project': snapshot.quota_deployments_per_project,
        'source_urls': dict(snapshot.source_urls),
        'promo_active': snapshot.promo_active,
        'promo_note': snapshot.promo_note,
        'model_count': len(snapshot.models),
    }



def _pricing_to_state(pricing: ModelPricing) -> dict:
    return {
        'input_price_per_1k': pricing.input_price_per_1k,
        'output_price_per_1k': pricing.output_price_per_1k,
        'input_price_per_1k_promo': pricing.input_price_per_1k_promo,
        'output_price_per_1k_promo': pricing.output_price_per_1k_promo,
        'billing_unit_tokens': pricing.billing_unit_tokens,
    }



def _pricing_from_state(data: dict) -> ModelPricing:
    return ModelPricing(
        input_price_per_1k=float(data['input_price_per_1k']),
        output_price_per_1k=(None if data.get('output_price_per_1k') is None else float(data['output_price_per_1k'])),
        input_price_per_1k_promo=(None if data.get('input_price_per_1k_promo') is None else float(data['input_price_per_1k_promo'])),
        output_price_per_1k_promo=(None if data.get('output_price_per_1k_promo') is None else float(data['output_price_per_1k_promo'])),
        billing_unit_tokens=int(data['billing_unit_tokens']),
    )



def _model_to_state(model: ModelInfo) -> dict:
    return {
        'name': model.name,
        'developer': model.developer,
        'input_formats': list(model.input_formats),
        'output_format': model.output_format,
        'context_k_tokens': model.context_k_tokens,
        'size_b_params': model.size_b_params,
        'pricing': _pricing_to_state(model.pricing) if model.pricing is not None else None,
    }



def _model_from_state(data: dict) -> ModelInfo:
    return ModelInfo(
        name=data['name'],
        developer=data['developer'],
        input_formats=tuple(data['input_formats']),
        output_format=data['output_format'],
        context_k_tokens=int(data['context_k_tokens']),
        size_b_params=float(data['size_b_params']),
        pricing=_pricing_from_state(data['pricing']) if data.get('pricing') is not None else None,
    )



def _estimate_to_state(estimate: CostEstimate | None) -> dict | None:
    if estimate is None:
        return None
    return {
        'input_tokens_monthly': estimate.input_tokens_monthly,
        'output_tokens_monthly': estimate.output_tokens_monthly,
        'monthly_24h_window_rub': estimate.monthly_24h_window_rub,
        'monthly_isolated_floor_rub': estimate.monthly_isolated_floor_rub,
        'input_billed_tokens_monthly_window': estimate.input_billed_tokens_monthly_window,
        'output_billed_tokens_monthly_window': estimate.output_billed_tokens_monthly_window,
        'tariff_input_per_1k': estimate.tariff_input_per_1k,
        'tariff_output_per_1k': estimate.tariff_output_per_1k,
        'billing_unit_tokens': estimate.billing_unit_tokens,
    }



def _estimate_from_state(data: dict | None) -> CostEstimate | None:
    if not data:
        return None
    return CostEstimate(
        input_tokens_monthly=data.get('input_tokens_monthly'),
        output_tokens_monthly=data.get('output_tokens_monthly'),
        monthly_24h_window_rub=data.get('monthly_24h_window_rub'),
        monthly_isolated_floor_rub=data.get('monthly_isolated_floor_rub'),
        input_billed_tokens_monthly_window=data.get('input_billed_tokens_monthly_window'),
        output_billed_tokens_monthly_window=data.get('output_billed_tokens_monthly_window'),
        tariff_input_per_1k=float(data['tariff_input_per_1k']),
        tariff_output_per_1k=(None if data.get('tariff_output_per_1k') is None else float(data['tariff_output_per_1k'])),
        billing_unit_tokens=int(data['billing_unit_tokens']),
    )



def recommendations_to_state(recommendations: list[Recommendation]) -> list[dict]:
    return [
        {
            'model': _model_to_state(rec.model),
            'score': rec.score,
            'reasons': list(rec.reasons),
            'warnings': list(rec.warnings),
            'estimate': _estimate_to_state(rec.estimate),
        }
        for rec in recommendations
    ]



def recommendations_from_state(data: list[dict] | None) -> list[Recommendation]:
    if not data:
        return []
    output: list[Recommendation] = []
    for item in data:
        output.append(
            Recommendation(
                model=_model_from_state(item['model']),
                score=float(item['score']),
                reasons=list(item.get('reasons', [])),
                warnings=list(item.get('warnings', [])),
                estimate=_estimate_from_state(item.get('estimate')),
            )
        )
    return output



def snapshot_from_meta(meta: dict, models: list[ModelInfo]) -> CatalogSnapshot:
    fetched_at_raw = meta.get('fetched_at')
    fetched_at = datetime.fromisoformat(fetched_at_raw) if fetched_at_raw else datetime.now(timezone.utc)
    return CatalogSnapshot(
        fetched_at=fetched_at,
        models=models,
        quota_deployments_per_project=meta.get('quota_deployments_per_project'),
        source_urls=dict(meta.get('source_urls', {})),
        promo_active=bool(meta.get('promo_active', False)),
        promo_note=meta.get('promo_note'),
    )
