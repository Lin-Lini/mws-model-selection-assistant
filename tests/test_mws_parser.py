from datetime import date
from pathlib import Path

from app.mws_parser import apply_pricing, parse_models_page, parse_pricing_page, parse_quota_page


FIXTURES = Path("tests/fixtures/mws")


def test_parse_models_page() -> None:
    models = parse_models_page((FIXTURES / "gpt-models.txt").read_text(encoding="utf-8"))
    assert len(models) == 10
    assert any(m.name == "gemma-3-27b-it" and m.supports_image_input for m in models)
    assert any(m.name == "bge-m3" and m.is_embedding for m in models)


def test_parse_pricing_page() -> None:
    result = parse_pricing_page((FIXTURES / "pricing.txt").read_text(encoding="utf-8"), today=date(2026, 4, 23))
    assert result.promo_active is True
    assert result.prices["qwen3-32b"].billing_unit_tokens == 100
    assert result.prices["bge-m3"].output_price_per_1k is None


def test_apply_pricing_and_quota() -> None:
    models = parse_models_page((FIXTURES / "gpt-models.txt").read_text(encoding="utf-8"))
    result = parse_pricing_page((FIXTURES / "pricing.txt").read_text(encoding="utf-8"), today=date(2026, 4, 23))
    enriched = apply_pricing(models, result.prices)
    quota = parse_quota_page((FIXTURES / "quotas-limits.txt").read_text(encoding="utf-8"))
    assert len(enriched) == 10
    assert quota == 10


def test_parse_pricing_page_without_spaces_between_ruble_cells() -> None:
    text = """# Тарификация
в период акции с 15 апреля по 15 июля
qwen3-32b 0,054 ₽0,219 ₽1,098 ₽1,098 ₽100
bge-m3 0,0006 ₽–0,0122 ₽–1000
"""
    result = parse_pricing_page(text, today=date(2026, 4, 23))
    assert result.prices["qwen3-32b"].billing_unit_tokens == 100
    assert result.prices["qwen3-32b"].input_per_1k == 1.098
    assert result.prices["bge-m3"].output_price_per_1k is None


def test_parse_models_page_from_cell_separated_html_text() -> None:
    text = """
Параметр
Разработчик
Формат ввода
Формат вывода
Контекст, в тысячах токенов
Размер модели, в млрд. параметров
deepseek-r1-distill-qwen-32b
DeepSeek
Text
Text
128
32
gemma-3-27b-it
Google
Text
Image
Text
128
27
bge-m3
BAAI
Text
Embedding
8
0.6
"""
    models = parse_models_page(text)
    assert len(models) == 3
    assert models[1].name == "gemma-3-27b-it"
    assert models[1].input_formats == ("Text", "Image")
    assert models[2].is_embedding is True


def test_parse_pricing_page_from_cell_separated_html_text() -> None:
    text = """
Модель
Цена за 1000 входящих токенов, с НДС 22% в период акции с 15 апреля по 15 июля
deepseek-r1-distill-qwen-32b
0,054 ₽
0,219 ₽
1,098 ₽
1,098 ₽
100
bge-m3
0,0006 ₽
–
0,0122 ₽
–
1000
"""
    result = parse_pricing_page(text, today=date(2026, 4, 23))
    assert result.prices["deepseek-r1-distill-qwen-32b"].input_per_1k == 1.098
    assert result.prices["bge-m3"].output_per_1k is None
    assert result.prices["bge-m3"].billing_unit_tokens == 1000


def test_parse_pricing_page_from_single_blob_with_header_and_rows() -> None:
    text = """
# Тарификация
Модель Цена за 1000 входящих токенов, с НДС 22% в период акции с 15 апреля по 15 июля Цена за 1000 исходящих токенов, с НДС 22% в период акции с 15 апреля по 15 июля Цена за 1000 входящих токенов, с НДС 22%Цена за 1000 исходящих токенов, с НДС 22%Отпускная единица, в токенах deepseek-r1-distill-qwen-32b 0,054 ₽0,219 ₽1,098 ₽1,098 ₽100 gemma-3-27b-it 0,054 ₽0,219 ₽1,098 ₽1,098 ₽100 bge-m3 0,0006 ₽–0,0122 ₽–1000
"""
    result = parse_pricing_page(text, today=date(2026, 4, 23))
    assert result.prices["deepseek-r1-distill-qwen-32b"].input_per_1k == 1.098
    assert result.prices["gemma-3-27b-it"].output_per_1k == 1.098
    assert result.prices["bge-m3"].billing_unit_tokens == 1000


def test_parse_pricing_page_without_separator_after_model_name() -> None:
    text = "qwen3-32b0,054 ₽0,219 ₽1,098 ₽1,098 ₽100"
    result = parse_pricing_page(text, today=date(2026, 4, 23))
    assert result.prices["qwen3-32b"].input_per_1k == 1.098
    assert result.prices["qwen3-32b"].output_per_1k == 1.098


def test_parse_pricing_page_with_mojibake_ruble_from_wrong_response_encoding() -> None:
    text = "qwen3-32b 0,054 â½0,219 â½1,098 â½1,098 â½100"
    result = parse_pricing_page(text, today=date(2026, 4, 23))
    assert result.prices["qwen3-32b"].input_per_1k == 1.098
    assert result.prices["qwen3-32b"].output_per_1k == 1.098
