from datetime import datetime, timezone
from pathlib import Path

from app.models import CatalogSnapshot
from app.mws_parser import apply_pricing, parse_models_page, parse_pricing_page, parse_quota_page
from app.recommender import recommend
from app.scenario_parser import parse_text_to_scenario


FIXTURES = Path("tests/fixtures/mws")


def _snapshot() -> CatalogSnapshot:
    models = parse_models_page((FIXTURES / "gpt-models.txt").read_text(encoding="utf-8"))
    pricing = parse_pricing_page((FIXTURES / "pricing.txt").read_text(encoding="utf-8"), today=datetime.now(timezone.utc).date())
    enriched = apply_pricing(models, pricing.prices)
    quota = parse_quota_page((FIXTURES / "quotas-limits.txt").read_text(encoding="utf-8"))
    return CatalogSnapshot(
        fetched_at=datetime.now(timezone.utc),
        models=enriched,
        quota_deployments_per_project=quota,
        source_urls={},
        promo_active=pricing.promo_active,
        promo_note=pricing.promo_note,
    )


def test_recommend_text_chat_models() -> None:
    scenario = parse_text_to_scenario(
        "Нужен чат-ассистент поддержки. Только текст. 1500 запросов в день. В среднем 1200 входящих и 500 исходящих токенов на запрос. Бюджет до 25000 ₽ в месяц. Нужен баланс цены и качества."
    )
    recs = recommend(_snapshot(), scenario)
    assert recs
    names = [r.model.name for r in recs]
    assert "bge-m3" not in names
    assert any(name in names for name in ["qwen3-32b", "gemma-3-27b-it", "deepseek-r1-distill-qwen-32b"])


def test_recommend_multimodal_only_image_capable() -> None:
    scenario = parse_text_to_scenario(
        "Нужен мультимодальный ассистент с изображениями. 100 запросов в день. 2000 входящих и 600 исходящих токенов. Бюджет 10000 ₽."
    )
    recs = recommend(_snapshot(), scenario)
    assert recs
    assert all(rec.model.supports_image_input for rec in recs)
