#!/usr/bin/env bash
set -euo pipefail

base_url="${BASE_URL:-http://localhost:8000}"

echo "[1/4] проверка healthcheck"
curl -s "$base_url/healthz" | jq . || curl -s "$base_url/healthz"

echo "[2/4] проверка метрик"
curl -s "$base_url/metrics" | jq . || curl -s "$base_url/metrics"

echo "[3/4] обычный ответ без stream"
curl -s "$base_url/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -H 'X-Session-Id: smoke-demo' \
  -d '{
    "model": "mws-model-selector",
    "messages": [{"role":"user","content":"Нужен чат-ассистент поддержки. Только текст. 1500 запросов в день. В среднем 1200 входящих и 500 исходящих токенов на запрос. Бюджет до 25000 ₽ в месяц. Нужен баланс цены и качества."}],
    "stream": false
  }' | jq . || true

echo "[4/4] потоковый ответ stream=true"
curl -N "$base_url/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "mws-model-selector",
    "messages": [{"role":"user","content":"Нужен мультимодальный ассистент с изображениями. 100 запросов в день. 2000 входящих и 600 исходящих токенов на запрос. Бюджет 10000 ₽."}],
    "stream": true
  }'
