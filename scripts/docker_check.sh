#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
export HOST_PORT="${HOST_PORT:-18000}"

echo "[1/5] очистка старых контейнеров"
docker compose down --remove-orphans

echo "[2/5] сборка Docker-образа"
docker compose build

echo "[3/5] запуск тестов внутри Docker"
docker compose run --rm tests

echo "[4/5] запуск сервиса и pentest-проверки"
docker compose up -d assistant
docker compose run --rm pentest

echo "[5/5] последние логи сервиса"
docker compose logs --tail=80 assistant
