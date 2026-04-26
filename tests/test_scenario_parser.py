from app.scenario_parser import parse_text_to_scenario


def test_parse_russian_paired_input_output_tokens() -> None:
    scenario = parse_text_to_scenario(
        "Нужен чат-ассистент. 500 запросов в день. 800 входящих и 200 исходящих токенов. Бюджет 10000 ₽."
    )

    assert scenario.use_case == "chatbot"
    assert scenario.requests == 500
    assert scenario.traffic_period == "day"
    assert scenario.input_tokens_per_request == 800
    assert scenario.output_tokens_per_request == 200
    assert scenario.budget_rub_monthly == 10000


def test_parse_russian_average_input_output_tokens() -> None:
    scenario = parse_text_to_scenario(
        "Нужен ассистент поддержки. 1500 запросов в день. В среднем 1200 входящих и 500 исходящих токенов на запрос. Бюджет до 25000 ₽."
    )

    assert scenario.input_tokens_per_request == 1200
    assert scenario.output_tokens_per_request == 500
