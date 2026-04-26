from __future__ import annotations

from datetime import date

from app.models import CatalogSnapshot, Recommendation, Scenario
from app.pricing import estimate_monthly_cost


def _use_case_reason(scenario: Scenario, model_name: str) -> list[str]:
    reasons: list[str] = []
    lower = model_name.lower()
    if scenario.use_case == "code_assistant" and "coder" in lower:
        reasons.append("Название и позиционирование модели указывает на пригодность для задач программирования.")
    if scenario.use_case == "multimodal_assistant":
        reasons.append("Модель поддерживает мультимодальный ввод, включая изображения.")
    if scenario.use_case == "chatbot":
        reasons.append("Подходит для обычного текстового диалога без режима эмбеддингов.")
    if scenario.use_case == "embeddings":
        reasons.append("Это модель для построения эмбеддингов, а не генеративная модель.")
    return reasons


def _quality_bonus(scenario: Scenario, model) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    if scenario.quality_preference == "budget":
        score += 10
        reasons.append("Сценарий чувствителен к цене, поэтому более дешевые модели получают приоритет.")
    elif scenario.quality_preference == "latency":
        if model.size_b_params <= 32:
            score += 10
            reasons.append("Для низкой задержки полезнее компактные модели.")
    elif scenario.quality_preference == "quality":
        if model.size_b_params >= 200:
            score += 10
            reasons.append("Приоритет на качество и большой контекст повышает более крупные модели.")
    elif scenario.quality_preference == "balanced":
        score += 6
        reasons.append("Запрошен баланс цены и качества, поэтому учитывается и стоимость, и размер/контекст.")
    return score, reasons


def recommend(snapshot: CatalogSnapshot, scenario: Scenario, top_k: int = 3) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for model in snapshot.models:
        warnings: list[str] = []
        reasons = _use_case_reason(scenario, model.name)

        if scenario.use_case != "embeddings" and model.is_embedding:
            continue
        if scenario.use_case == "embeddings" and not model.is_embedding:
            continue
        if scenario.needs_image_input and not model.supports_image_input:
            continue

        score = 40.0

        if scenario.use_case == "code_assistant" and "coder" in model.name.lower():
            score += 20
        if scenario.use_case == "multimodal_assistant" and model.supports_image_input:
            score += 20
        if scenario.use_case == "chatbot" and not model.is_embedding:
            score += 10
        if scenario.use_case == "embeddings" and model.is_embedding:
            score += 15

        quality_score, quality_reasons = _quality_bonus(scenario, model)
        score += quality_score
        reasons.extend(quality_reasons)

        if scenario.input_tokens_per_request is not None:
            out_tokens = 0 if model.is_embedding else (scenario.output_tokens_per_request or 0)
            required_context_k = (scenario.input_tokens_per_request + out_tokens) / 1000.0
            if model.context_k_tokens >= required_context_k * 2:
                score += 15
                reasons.append("Есть запас по контекстному окну относительно среднего запроса.")
            elif model.context_k_tokens >= required_context_k:
                score += 5
                reasons.append("Контекстного окна достаточно для указанного размера запроса.")
            else:
                score -= 100
                warnings.append("Контекстное окно выглядит недостаточным для описанного сценария.")

        estimate = estimate_monthly_cost(
            scenario,
            model,
            promo_active=snapshot.promo_active,
            today=date.today(),
        )
        if estimate is not None and scenario.budget_rub_monthly is not None:
            budget = scenario.budget_rub_monthly
            if estimate.monthly_24h_window_rub is not None and estimate.monthly_24h_window_rub <= budget:
                score += 20
                reasons.append("Оценка месячной стоимости укладывается в бюджет.")
            elif estimate.monthly_isolated_floor_rub is not None and estimate.monthly_isolated_floor_rub <= budget:
                score += 5
                warnings.append("В бюджет модель укладывается только при разреженном трафике.")
            else:
                score -= 40
                warnings.append("По оценке месячной стоимости модель выходит за бюджет.")

        if model.size_b_params <= 32:
            score += 5
        if model.context_k_tokens >= 128:
            score += 3

        recs.append(Recommendation(model=model, score=score, reasons=reasons, warnings=warnings, estimate=estimate))

    recs.sort(
        key=lambda item: (
            item.score,
            -(item.estimate.monthly_24h_window_rub or 10**9) if item.estimate else 0,
        ),
        reverse=True,
    )
    return recs[:top_k]
