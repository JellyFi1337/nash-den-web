# Образ сайта: base — зависимости выполнения, dev — тесты и ruff, prod — gunicorn.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    RUFF_CACHE_DIR=/tmp/ruff_cache \
    TZ=Europe/Moscow

ENV RES_OPTIONS="timeout:1 attempts:1"

COPY --from=ghcr.io/astral-sh/uv:python3.12-bookworm-slim /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /app

# postgresql-client-17 нужен, чтобы очистка сама писала pg_dump той же версии, что и база.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg tzdata \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --home-dir /home/app app

# Код и зависимости остаются у root: процесс их читает, но не переписывает.
# chown -R по /app копировал всё дерево, включая .venv, отдельным слоем.
COPY --chown=root:root pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=root:root src ./src
COPY --chown=root:root scripts ./scripts
COPY --chown=root:root docker/web/entrypoint.sh /app/entrypoint.sh
# Сборка на Windows может принести CRLF; в контейнере скрипт запускается через sh.
# Писать процесс может только в загрузки, собранную статику и кэши проверок.
RUN sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod 755 /app/entrypoint.sh \
    && mkdir -p /app/media /app/staticfiles /tmp/ruff_cache /tmp/pytest_cache \
    && chown app:app /app/media /app/staticfiles /tmp/ruff_cache /tmp/pytest_cache

USER app
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]

FROM base AS dev

USER root
RUN uv sync --frozen --no-install-project
USER app
CMD ["python", "/app/src/manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS prod

# Секрет сборки не сохраняется в образ: переменные действуют только на эту команду.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=collectstatic-build-only \
    DJANGO_ALLOWED_HOSTS=localhost \
    POSTGRES_DB=build \
    POSTGRES_USER=build \
    POSTGRES_PASSWORD=build \
    POSTGRES_HOST=127.0.0.1 \
    POSTGRES_PORT=5432 \
    python /app/src/manage.py collectstatic --noinput

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-"]
