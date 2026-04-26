from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from app.config import Settings
from app.memory import SessionStore
from app.models import CatalogSnapshot
from app.mws_parser import apply_pricing, parse_models_page, parse_pricing_page, parse_quota_page

logger = logging.getLogger(__name__)

MWS_URLS = {
    "models": "https://mws.ru/docs/cloud-platform/gpt/general/gpt-models.html",
    "pricing": "https://mws.ru/docs/cloud-platform/gpt/general/pricing.html",
    "quotas": "https://mws.ru/docs/cloud-platform/gpt/general/quotas-limits.html",
}


class MwsClient:
    def __init__(self, settings: Settings, session_store: SessionStore, metrics: dict[str, float | int]) -> None:
        self.settings = settings
        self.session_store = session_store
        self.metrics = metrics

    def get_catalog(self, session_id: str | None) -> CatalogSnapshot:
        if session_id:
            session = self.session_store.get_or_create(session_id)
            if session.catalog is not None:
                self.metrics["cache_hits"] = int(self.metrics.get("cache_hits", 0)) + 1
                return session.catalog

        self.metrics["cache_misses"] = int(self.metrics.get("cache_misses", 0)) + 1
        texts = self._fetch_pages()
        parsed_models = parse_models_page(texts["models"])
        pricing = parse_pricing_page(texts["pricing"], today=date.today())
        models = apply_pricing(parsed_models, pricing.prices)
        quota = parse_quota_page(texts["quotas"])

        missing_prices = [model.name for model in models if model.pricing is None]
        if missing_prices:
            logger.warning("Для части моделей MWS не найдены тарифы: %s", ", ".join(missing_prices))

        snapshot = CatalogSnapshot(
            fetched_at=datetime.now(timezone.utc),
            models=models,
            quota_deployments_per_project=quota,
            source_urls=MWS_URLS.copy(),
            promo_active=pricing.promo_active,
            promo_note=pricing.promo_note,
        )
        if session_id:
            self.session_store.get_or_create(session_id).catalog = snapshot
        return snapshot

    def _fetch_pages(self) -> dict[str, str]:
        if self.settings.fixture_dir:
            return self._read_fixture_dir(self.settings.fixture_dir)

        import requests

        texts: dict[str, str] = {}
        headers = {"User-Agent": "mws-model-selection-assistant/0.1"}
        for key, url in MWS_URLS.items():
            started = datetime.now(timezone.utc)
            response = requests.get(url, headers=headers, timeout=self.settings.request_timeout_seconds)
            response.raise_for_status()
            html = self._decode_response_body(response)
            texts[key] = self._html_to_text(html)
            self.metrics["mws_fetches"] = int(self.metrics.get("mws_fetches", 0)) + 1
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
            logger.info("получена страница MWS key=%s status=%s elapsed_ms=%.2f", key, response.status_code, elapsed)
        return texts


    @staticmethod
    def _decode_response_body(response: object) -> str:
        content = getattr(response, "content", b"")
        if isinstance(content, bytes) and content:
            return content.decode("utf-8", errors="replace")

        text = getattr(response, "text", "")
        return text if isinstance(text, str) else str(text)

    @staticmethod
    def _html_to_text(html: str) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        table_rows: list[str] = []
        for row in soup.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if cells:
                table_rows.append(" ".join(cells))

        # Сохраняем и восстановленные строки таблиц, и обычный текст страницы.
        # Это повышает устойчивость парсинга к разному HTML-формату MWS
        # без хардкода каталога моделей или тарифов.
        body_text = soup.get_text("\n")
        return "\n".join([*table_rows, body_text])

    @staticmethod
    def _read_fixture_dir(path: Path) -> dict[str, str]:
        mapping = {
            "models": path / "gpt-models.txt",
            "pricing": path / "pricing.txt",
            "quotas": path / "quotas-limits.txt",
        }
        output: dict[str, str] = {}
        for key, file_path in mapping.items():
            output[key] = file_path.read_text(encoding="utf-8")
        return output
