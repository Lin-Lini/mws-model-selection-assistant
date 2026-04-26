FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-dev.txt

COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY README.md pyproject.toml ./

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && chown -R app:app /app

USER app

ENV HOST=0.0.0.0 \
    PORT=8000 \
    LOG_LEVEL=INFO

EXPOSE 8000

CMD ["python", "-m", "app.server"]
