from __future__ import annotations

import json
import re

from app.models import Scenario


_JSON_KEYS = {
    "use_case",
    "traffic",
    "budget_rub",
    "budget_rub_monthly",
    "quality_preference",
    "input_tokens_per_request",
    "output_tokens_per_request",
}


def _norm(s: str) -> str:
    s = s.replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _num(s: str) -> int | None:
    s = s.replace(" ", "")
    if not s:
        return None
    try:
        v = int(s)
    except ValueError:
        return None
    return v if v >= 0 else None


def _money(s: str) -> float | None:
    raw = s.strip().lower()
    mult = 1.0
    if any(x in raw for x in ["тыс", "k", "к"]):
        mult = 1000.0
    raw = re.sub(r"[^0-9,.-]", "", raw).replace(" ", "").replace(",", ".")
    try:
        v = float(raw) * mult
    except ValueError:
        return None
    return v if v >= 0 else None


def _use_case(t: str) -> str:
    if any(x in t for x in ["эмбед", "embedding", "вектор", "поиск по базе знаний", "по базе знаний"]):
        return "embeddings"
    if any(x in t for x in ["мультимод", "изображ", "картин", "image"]):
        return "multimodal_assistant"
    if any(x in t for x in ["код", "code assistant", "copilot", "ide", "разработк", "coder"]):
        return "code_assistant"
    if any(x in t for x in ["аналит", "analysis", "отчет", "сводк", "summary", "summari", "классификац"]):
        return "analysis"
    if any(x in t for x in ["чат", "chatbot", "поддержк", "ассистент поддержки", "support"]):
        return "chatbot"
    return "unknown"


def _quality(t: str) -> str:
    if any(x in t for x in ["баланс", "balanced", "price quality", "цены и качества", "цена/качество"]):
        return "balanced"
    if any(x in t for x in ["быстр", "задержк", "latency", "низкая latency"]):
        return "latency"
    if any(x in t for x in ["максимальное качество", "лучшее качество", "best quality", "точност", "quality"]):
        return "quality"
    if any(x in t for x in ["недорог", "дешев", "эконом", "минимальная стоимость", "budget option"]):
        return "budget"
    return "unknown"


def _traffic(t: str) -> tuple[int | None, str]:
    pats = [
        r"(\d[\d ]*)\s*(?:запрос(?:ов|а)?|req(?:uests?)?|сообщен(?:ий|ия)|диалог(?:ов|а)?)\s*(?:в|/)\s*(день|сутки|day|месяц|month)",
        r"(\d[\d ]*)\s*(?:текст(?:ов|а)?|документ(?:ов|а)?|запис(?:ей|ь))\s*(?:в|/)\s*(день|day|месяц|month)",
    ]
    for p in pats:
        m = re.search(p, t)
        if not m:
            continue
        n = _num(m.group(1))
        if n is None:
            return None, "unknown"
        per = m.group(2)
        if per in {"месяц", "month"}:
            return n, "month"
        return n, "day"
    return None, "unknown"


def _in_tokens(t: str, uc: str) -> int | None:
    pats = [
        r"(\d[\d ]*)\s*(?:входящ(?:их|ие|ий)|входн(?:ых|ые|ый)|input)\s*(?:(?:и|,|;|/|\+)\s*\d|токен|$)",
        r"средн(?:ий|ее|яя)?\s*(?:вход|input)\s*[:=\-]?\s*(\d[\d ]*)",
        r"(?:вход|input)\s*[:=\-]?\s*(\d[\d ]*)\s*токен",
        r"в среднем\s*(\d[\d ]*)\s*токен(?:ов|а)?\s*на\s*(?:запрос|документ)",
        r"(\d[\d ]*)\s*токен(?:ов|а)?\s*на\s*(?:запрос|документ)",
    ]
    for p in pats:
        m = re.search(p, t)
        if not m:
            continue
        v = _num(m.group(1))
        if v is not None:
            return v
    if uc == "embeddings":
        m = re.search(r"в среднем\s*(\d[\d ]*)\s*токен(?:ов|а)?", t)
        if m:
            return _num(m.group(1))
    return None


def _out_tokens(t: str, uc: str) -> int | None:
    if uc == "embeddings":
        return 0
    pats = [
        r"(\d[\d ]*)\s*(?:исходящ(?:их|ие|ий)|выходн(?:ых|ые|ый)|output)\s*(?:токен|$)",
        r"и\s*(\d[\d ]*)\s*(?:исходящ(?:их|ие|ий)|выходн(?:ых|ые|ый)|output)",
        r"средн(?:ий|ее|яя)?\s*(?:выход|output)\s*[:=\-]?\s*(\d[\d ]*)",
        r"(?:выход|output)\s*[:=\-]?\s*(\d[\d ]*)\s*токен",
    ]
    for p in pats:
        m = re.search(p, t)
        if not m:
            continue
        v = _num(m.group(1))
        if v is not None:
            return v
    return None


def _budget(t: str) -> float | None:
    m = re.search(
        r"(?:бюджет(?:\s*до)?|budget(?:\s*up to)?|до)\s*([-]?\d[\d ]*(?:[.,]\d+)?\s*(?:тыс\.?|k|к)?)\s*(?:руб|₽|rub)?",
        t,
    )
    if not m:
        return None
    return _money(m.group(1))


def scenario_from_text(text: str) -> Scenario:
    t = _norm(text)
    uc = _use_case(t)
    rq, per = _traffic(t)
    inp = _in_tokens(t, uc)
    out = _out_tokens(t, uc)
    bud = _budget(t)
    q = _quality(t)
    img = uc == "multimodal_assistant" or any(x in t for x in ["изображ", "image", "картин", "photo", "jpeg", "png"])

    return Scenario(
        use_case=uc,
        traffic_period=per,
        requests=rq,
        input_tokens_per_request=inp,
        output_tokens_per_request=out,
        budget_rub_monthly=bud,
        quality_preference=q,
        needs_image_input=img,
    )


def scenario_from_dict(data: dict) -> Scenario:
    use_case = str(data.get("use_case", "unknown"))
    if use_case not in {"chatbot", "code_assistant", "multimodal_assistant", "analysis", "embeddings", "unknown"}:
        use_case = "unknown"

    traffic = data.get("traffic", {}) or {}
    per = str(traffic.get("period", "unknown"))
    if per not in {"day", "month", "unknown"}:
        per = "unknown"

    req = traffic.get("requests", data.get("requests"))
    req = req if isinstance(req, int) and req >= 0 else None

    inp = data.get("input_tokens_per_request", traffic.get("input_tokens_per_request"))
    inp = inp if isinstance(inp, int) and inp >= 0 else None

    out = data.get("output_tokens_per_request", traffic.get("output_tokens_per_request"))
    if use_case == "embeddings":
        out = 0
    else:
        out = out if isinstance(out, int) and out >= 0 else None

    bud = data.get("budget_rub_monthly", data.get("budget_rub", data.get("budget")))
    bud = float(bud) if isinstance(bud, (int, float)) and bud >= 0 else None

    q = str(data.get("quality_preference", "unknown"))
    if q not in {"quality", "balanced", "budget", "latency", "unknown"}:
        q = "unknown"

    return Scenario(
        use_case=use_case,
        traffic_period=per,
        requests=req,
        input_tokens_per_request=inp,
        output_tokens_per_request=out,
        budget_rub_monthly=bud,
        quality_preference=q,
        needs_image_input=bool(data.get("needs_image_input", False)),
    )


def _try_parse_json_message(text: str) -> Scenario | None:
    raw = text.strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not any(k in data for k in _JSON_KEYS):
        return None
    return scenario_from_dict(data)


def parse_messages(messages) -> Scenario:
    merged = Scenario()
    for msg in messages:
        if getattr(msg, "role", None) != "user":
            continue
        text = getattr(msg, "content", "") or ""
        parsed = _try_parse_json_message(text)
        if parsed is None:
            parsed = scenario_from_text(text)
        merged = merged.merge(parsed)
    return merged


parse_text_to_scenario = scenario_from_text
parse_scenario_text = scenario_from_text
parse_text_scenario = scenario_from_text
parse_scenario_dict = scenario_from_dict
