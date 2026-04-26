from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class WorkflowDescription:
    pattern: str
    roles: list[str]
    notes: list[str]


def build_description() -> WorkflowDescription:
    return WorkflowDescription(
        pattern="Последовательный агентный сценарий SequentialAgent в Google ADK",
        roles=[
            "IntakeAgent извлекает сценарий пользователя из сообщений OpenAI-совместимого чата и объединяет его с состоянием сессии.",
            "CatalogAgent получает актуальные данные MWS по моделям, тарифам и лимитам и приводит их к единому внутреннему формату.",
            "RecommendationAgent ранжирует подходящие модели и рассчитывает примерную месячную стоимость использования.",
            "ReportAgent формирует итоговый структурированный отчёт, который возвращается через OpenAI-совместимый API.",
        ],
        notes=[
            "Описание соответствует реальному runtime, реализованному в app/adk_runtime.py.",
            "Агентный сценарий построен на ADK, при этом расчёты стоимости и ранжирование остаются детерминированными и проверяемыми.",
        ],
    )
