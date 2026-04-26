from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import date

from app.models import ModelInfo, ModelPricing

_LINK_RE = re.compile(r"【\d+†([^†】]+)(?:†[^】]+)?】")
_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_MODEL_ROW_RE = re.compile(
    r"^(?P<name>[a-zA-Z0-9._-]+)\s+"
    r"(?P<developer>.+?)\s+"
    r"(?P<input>Text(?:\s*,\s*Image)?|Image(?:\s*,\s*Text)?)\s+"
    r"(?P<output>Text|Embedding)\s+"
    r"(?P<context>\d+(?:[.,]\d+)?)\s+"
    r"(?P<size>\d+(?:[.,]\d+)?)$"
)
_PRICE_NAME_RE = re.compile(r"^(?P<name>[a-zA-Z0-9._-]+)\s+(?P<rest>.+)$")
_PRICE_ROW_BLOB_RE = re.compile(
    r"(?P<name>[a-zA-Z0-9._-]+)\s*"
    r"(?P<promo_in>\d+(?:[,.]\d+)?)\s*₽\s*"
    r"(?P<promo_out>\d+(?:[,.]\d+)?|[–—-])\s*(?:₽)?\s*"
    r"(?P<base_in>\d+(?:[,.]\d+)?)\s*₽\s*"
    r"(?P<base_out>\d+(?:[,.]\d+)?|[–—-])\s*(?:₽)?\s*"
    r"(?P<unit>\d+)"
)
_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_NUMBER_RE = re.compile(r"^\d+(?:[,.]\d+)?$")
_FORMATS = {"Text", "Image", "Embedding"}
_MONEY_OR_DASH_RE = re.compile(r"\d+(?:[,.]\d+)?|[–—-]")
_PROMO_RE = re.compile(
    r"с\s+(\d{1,2})\s+([а-яё]+)\s+по\s+(\d{1,2})\s+([а-яё]+)",
    re.IGNORECASE,
)
_QUOTA_RE = re.compile(
    r"Количество\s+развернутых\s+моделей\s+для\s+одного\s+проекта\s+(\d+)",
    re.IGNORECASE,
)

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


@dataclass(slots=True)
class PriceInfo:
    input_per_1k: float
    output_per_1k: float | None
    billing_unit_tokens: int
    promo_input_per_1k: float | None = None
    promo_output_per_1k: float | None = None

    @property
    def input_price_per_1k(self) -> float:
        return self.input_per_1k

    @property
    def output_price_per_1k(self) -> float | None:
        return self.output_per_1k


@dataclass(slots=True)
class PricingParseResult:
    prices: dict[str, PriceInfo]
    promo_active: bool
    promo_note: str | None


def _normalize_line(line: str) -> str:
    line = _LINK_RE.sub(lambda m: f" {m.group(1)} ", line)
    line = line.replace("`", " ")
    line = line.replace("\u200b", " ")
    line = line.replace("\ufeff", " ")
    line = line.replace("â\x82½", "₽")
    line = line.replace("â½", "₽")
    line = line.replace("â€“", "–")
    line = line.replace("â€”", "—")
    line = line.replace("&nbsp;", " ")
    line = _SPACE_RE.sub(" ", line)
    return line.strip()


def _normalized_lines(text: str) -> list[str]:
    return [line for raw in text.splitlines() if (line := _normalize_line(raw))]


def _parse_decimal(value: str) -> float:
    return float(value.replace("₽", "").replace(" ", "").replace(",", "."))


def _parse_money(value: str) -> float | None:
    value = value.strip().replace("₽", "").replace(" ", "")
    if value in {"–", "-", "—", ""}:
        return None
    return _parse_decimal(value)


def _append_model(
    models: list[ModelInfo],
    seen: set[str],
    *,
    name: str,
    developer: str,
    input_formats: tuple[str, ...],
    output_format: str,
    context: str,
    size: str,
) -> None:
    if name in seen:
        return
    seen.add(name)
    models.append(
        ModelInfo(
            name=name,
            developer=developer.strip(),
            input_formats=input_formats,
            output_format=output_format,
            context_k_tokens=int(_parse_decimal(context)),
            size_b_params=_parse_decimal(size),
        )
    )


def _looks_like_model_name(value: str) -> bool:
    if not _NAME_RE.match(value):
        return False
    if value in _FORMATS:
        return False
    return any(ch.isdigit() for ch in value) or "-" in value


def _parse_models_from_cells(lines: list[str], models: list[ModelInfo], seen: set[str]) -> None:
    i = 0
    while i < len(lines):
        name = lines[i]
        if not _looks_like_model_name(name):
            i += 1
            continue

        try:
            developer = lines[i + 1]
            j = i + 2
            if j < len(lines) and lines[j] == "*":
                developer = f"{developer} *"
                j += 1

            if lines[j] == "Text" and j + 4 < len(lines) and lines[j + 1] == "Image":
                input_formats = ("Text", "Image")
                output_format = lines[j + 2]
                context = lines[j + 3]
                size = lines[j + 4]
                next_i = j + 5
            else:
                input_formats = (lines[j],)
                output_format = lines[j + 1]
                context = lines[j + 2]
                size = lines[j + 3]
                next_i = j + 4

            if (
                all(fmt in {"Text", "Image"} for fmt in input_formats)
                and output_format in {"Text", "Embedding"}
                and _NUMBER_RE.match(context)
                and _NUMBER_RE.match(size)
            ):
                _append_model(
                    models,
                    seen,
                    name=name,
                    developer=developer,
                    input_formats=input_formats,
                    output_format=output_format,
                    context=context,
                    size=size,
                )
                i = next_i
                continue
        except IndexError:
            break

        i += 1


def parse_models_page(text: str) -> list[ModelInfo]:
    models: list[ModelInfo] = []
    seen: set[str] = set()
    lines = _normalized_lines(text)

    for line in lines:
        match = _MODEL_ROW_RE.match(line)
        if not match:
            continue

        input_formats = tuple(part.strip() for part in match.group("input").split(","))
        _append_model(
            models,
            seen,
            name=match.group("name"),
            developer=match.group("developer"),
            input_formats=input_formats,
            output_format=match.group("output"),
            context=match.group("context"),
            size=match.group("size"),
        )

    _parse_models_from_cells(lines, models, seen)

    if not models:
        raise ValueError("failed to parse models page")
    return models


def _price_tokens(rest: str) -> list[str]:
    rest = rest.replace("₽", " ₽ ")
    rest = rest.replace("–", " – ").replace("—", " – ")
    return [token for token in _MONEY_OR_DASH_RE.findall(rest) if token != "₽"]


def _build_price_info(
    *,
    promo_in: str,
    promo_out: str,
    base_in: str,
    base_out: str,
    unit: str,
) -> PriceInfo | None:
    unit = unit.strip().replace(" ", "")
    if unit in {"–", "-", "—", ""} or not _NUMBER_RE.match(unit):
        return None

    return PriceInfo(
        input_per_1k=_parse_money(base_in) or 0.0,
        output_per_1k=_parse_money(base_out),
        billing_unit_tokens=int(_parse_decimal(unit)),
        promo_input_per_1k=_parse_money(promo_in),
        promo_output_per_1k=_parse_money(promo_out),
    )


def _parse_price_line(line: str) -> tuple[str, PriceInfo] | None:
    line = _normalize_line(line)
    if "₽" not in line:
        return None

    blob_match = _PRICE_ROW_BLOB_RE.search(line)
    if blob_match and _looks_like_model_name(blob_match.group("name")):
        price = _build_price_info(
            promo_in=blob_match.group("promo_in"),
            promo_out=blob_match.group("promo_out"),
            base_in=blob_match.group("base_in"),
            base_out=blob_match.group("base_out"),
            unit=blob_match.group("unit"),
        )
        if price is not None:
            return blob_match.group("name"), price

    match = _PRICE_NAME_RE.match(line)
    if not match:
        return None

    tokens = _price_tokens(match.group("rest"))
    if len(tokens) < 5:
        return None

    promo_in, promo_out, base_in, base_out, unit = tokens[:5]
    price = _build_price_info(
        promo_in=promo_in,
        promo_out=promo_out,
        base_in=base_in,
        base_out=base_out,
        unit=unit,
    )
    if price is None:
        return None
    return match.group("name"), price


def _parse_prices_from_blob(text: str, prices: dict[str, PriceInfo]) -> None:
    normalized = _normalize_line(text)
    for match in _PRICE_ROW_BLOB_RE.finditer(normalized):
        name = match.group("name")
        if not _looks_like_model_name(name):
            continue

        price = _build_price_info(
            promo_in=match.group("promo_in"),
            promo_out=match.group("promo_out"),
            base_in=match.group("base_in"),
            base_out=match.group("base_out"),
            unit=match.group("unit"),
        )
        if price is not None:
            prices[name] = price


def _parse_prices_from_cells(lines: list[str], prices: dict[str, PriceInfo]) -> None:
    i = 0
    while i < len(lines):
        name = lines[i]
        if not _looks_like_model_name(name):
            i += 1
            continue
        if i + 5 >= len(lines):
            break

        cells = lines[i + 1 : i + 6]
        if not any("₽" in cell for cell in cells[:4]):
            i += 1
            continue
        unit = cells[4].replace(" ", "")
        if not _NUMBER_RE.match(unit):
            i += 1
            continue

        price = _build_price_info(
            promo_in=cells[0],
            promo_out=cells[1],
            base_in=cells[2],
            base_out=cells[3],
            unit=unit,
        )
        if price is not None:
            prices[name] = price
            i += 6
            continue
        i += 1


def _parse_promo_window(text: str, today: date) -> tuple[bool, str | None]:
    normalized = _normalize_line(text.lower())
    match = _PROMO_RE.search(normalized)
    if not match:
        return False, None

    start_day = int(match.group(1))
    start_month = _MONTHS.get(match.group(2))
    end_day = int(match.group(3))
    end_month = _MONTHS.get(match.group(4))
    if not start_month or not end_month:
        return False, None

    start = date(today.year, start_month, start_day)
    end = date(today.year, end_month, end_day)
    if end < start:
        end = date(today.year + 1, end_month, end_day)

    return start <= today <= end, f"Промо-период: с {start_day} {match.group(2)} по {end_day} {match.group(4)}"


def parse_pricing_page(text: str, today: date) -> PricingParseResult:
    prices: dict[str, PriceInfo] = {}
    lines = _normalized_lines(text)

    for line in lines:
        parsed = _parse_price_line(line)
        if parsed is None:
            continue
        name, price = parsed
        prices[name] = price

    _parse_prices_from_cells(lines, prices)
    _parse_prices_from_blob(text, prices)

    if not prices:
        raise ValueError("failed to parse pricing page")

    promo_active, promo_note = _parse_promo_window(text, today=today)
    return PricingParseResult(prices=prices, promo_active=promo_active, promo_note=promo_note)


def parse_quota_page(text: str) -> int | None:
    normalized = "\n".join(_normalized_lines(text))
    match = _QUOTA_RE.search(normalized)
    return int(match.group(1)) if match else None


def apply_pricing(models: list[ModelInfo], prices: dict[str, PriceInfo]) -> list[ModelInfo]:
    result: list[ModelInfo] = []
    for model in models:
        price = prices.get(model.name)
        if price is None:
            result.append(model)
            continue
        result.append(
            dataclasses.replace(
                model,
                pricing=ModelPricing(
                    input_price_per_1k=price.input_per_1k,
                    output_price_per_1k=price.output_per_1k,
                    input_price_per_1k_promo=price.promo_input_per_1k,
                    output_price_per_1k_promo=price.promo_output_per_1k,
                    billing_unit_tokens=price.billing_unit_tokens,
                ),
            )
        )
    return result
