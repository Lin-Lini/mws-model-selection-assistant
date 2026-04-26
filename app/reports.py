from __future__ import annotations

from app.models import CatalogSnapshot, Recommendation, Scenario


def _call(v):
    return v() if callable(v) else v


def _get(obj, *names):
    for n in names:
        if hasattr(obj, n):
            return _call(getattr(obj, n))
    return None


def _fmt_money(v: float | None) -> str:
    if v is None:
        return "н/д"
    return f"{v:,.2f} ₽".replace(",", " ")


def _fmt_io(v: str) -> str:
    return {
        "Text": "текст",
        "Image": "изображение",
        "Embedding": "эмбеддинги",
    }.get(v, v)


def _fmt_io_list(vs) -> str:
    return ", ".join(_fmt_io(v) for v in vs)


def _fmt_use_case(v: str) -> str:
    return {
        "chatbot": "чат-ассистент",
        "code_assistant": "кодовый ассистент",
        "multimodal_assistant": "мультимодальный ассистент",
        "analysis": "аналитический сценарий",
        "embeddings": "эмбеддинги",
        "unknown": "не указан",
    }.get(v, v)


def _fmt_quality(v: str) -> str:
    return {
        "quality": "качество",
        "balanced": "баланс",
        "budget": "экономия",
        "latency": "скорость",
        "unknown": "не указан",
    }.get(v, v)


def _fmt_int(v: float | int | None) -> str:
    if v is None:
        return "н/д"
    return f"{int(v):,}".replace(",", " ")


def _req(s: Scenario):
    return _get(s, "requests", "requests_per_period", "requests_count")


def _period(s: Scenario):
    return _get(s, "traffic_period") or "unknown"


def _inp(s: Scenario):
    return _get(s, "avg_input_tokens", "input_tokens_per_request")


def _out(s: Scenario):
    return _get(s, "avg_output_tokens", "output_tokens_per_request")


def _budget(s: Scenario):
    return _get(s, "budget_rub_monthly", "monthly_budget_rub")


def _prio(s: Scenario):
    return _get(s, "quality_preference") or "unknown"


def _use_case(s: Scenario):
    return _get(s, "use_case") or "unknown"


def build_missing_data_prompt(s: Scenario) -> str:
    miss = []
    if _req(s) is None:
        miss.append("объем трафика")
    if _inp(s) is None:
        miss.append("средний вход")
    if _use_case(s) != "embeddings" and _out(s) is None:
        miss.append("средний выход")
    return (
        "Нужно уточнить входные данные, иначе расчет будет фикцией. "
        f"Не хватает: {', '.join(miss)}. "
        "Можно прислать вводные обычным текстом или JSON с полями use_case, traffic, budget."
    )


def build_report(s: Scenario, recs: list[Recommendation], snap: CatalogSnapshot) -> str:
    lines: list[str] = []

    uc = _use_case(s)
    rq = _req(s)
    pr = _period(s)
    inp = _inp(s)
    out = _out(s)
    bud = _budget(s)
    q = _prio(s)

    period_text = "день" if pr == "day" else "месяц" if pr == "month" else "не указанный период"

    lines.append("Входные данные")
    lines.append(f"- Тип кейса: {_fmt_use_case(uc)}")
    lines.append(f"- Трафик: {_fmt_int(rq)} запросов в {period_text}")
    lines.append(f"- Средний вход: {_fmt_int(inp)} токенов/запрос")
    if uc == "embeddings":
        lines.append("- Средний выход: не требуется")
    else:
        lines.append(f"- Средний выход: {_fmt_int(out)} токенов/запрос")
    lines.append(f"- Бюджет: {_fmt_money(bud)} / месяц")
    lines.append(f"- Приоритет: {_fmt_quality(q)}")
    lines.append("")

    lines.append("Рекомендованные модели")
    if not recs:
        lines.append("- Не удалось подобрать модель по текущим ограничениям. Уточните входные токены, выходные токены, бюджет или требуемую модальность.")
    else:
        for i, r in enumerate(recs, start=1):
            m = r.model
            lines.append(
                f"{i}. {m.name} | разработчик={m.developer} | вход={_fmt_io_list(m.input_formats)} | выход={_fmt_io(m.output_format)} | контекст={m.context_k_tokens}k"
            )
            for x in r.reasons[:4]:
                lines.append(f"   - {x}")
            for x in r.warnings[:2]:
                lines.append(f"   - Ограничение: {x}")
    lines.append("")

    lines.append("Расчеты")
    if not recs:
        lines.append("- Нет расчетов: не хватает пригодных кандидатов или обязательных входных данных.")
    else:
        for r in recs:
            e = r.estimate
            if e is None:
                lines.append(f"- {r.model.name}: недостаточно данных для расчета стоимости.")
                continue
            lines.append(
                f"- {r.model.name}: оценка за 24 часа={_fmt_money(e.monthly_24h_window_rub)}, минимальная оценка при редких запросах={_fmt_money(e.monthly_isolated_floor_rub)}"
            )
            lines.append(
                f"  тарифы: вход={e.tariff_input_per_1k} ₽/1000 токенов, выход={e.tariff_output_per_1k if e.tariff_output_per_1k is not None else '—'} ₽/1000 токенов, единица тарификации={e.billing_unit_tokens}"
            )
    lines.append("")

    lines.append("Пояснения и ограничения")
    lines.append("- Источник цен и списка моделей: документация MWS, полученная во время запроса. В тестовом режиме могут использоваться локальные локальные фикстуры.")
    if getattr(snap, "promo_note", None):
        st = "акция активна" if getattr(snap, "promo_active", False) else "акция неактивна для текущей даты"
        lines.append(f"- {snap.promo_note}. Статус: {st}.")
    if getattr(snap, "quota_deployments_per_project", None) is not None:
        lines.append(f"- Квота MWS: до {snap.quota_deployments_per_project} развернутых моделей на проект по умолчанию.")
    if getattr(snap, "source_urls", None):
        lines.append("- Использованные страницы MWS: " + ", ".join(f"{k}={v}" for k, v in snap.source_urls.items()) + ".")
    lines.append("- Оценка за 24 часа предполагает накопление токенов в пределах суток до кратности отпускной единице.")
    lines.append("- Минимальная оценка при редких запросах показывает нижнюю границу, когда остатки токенов могут сгореть через 24 часа.")
    lines.append("- Один и тот же текст может токенизироваться по-разному у разных моделей, поэтому итоговая стоимость всегда приблизительная.")

    return "\n".join(lines)
