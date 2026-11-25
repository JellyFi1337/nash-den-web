#!/bin/sh
# Ждёт базу, в разработке на сервисе web накатывает миграции и запускает команду.
set -eu

python - <<'PY'
import os
import sys
import time

import psycopg

host = os.environ["POSTGRES_HOST"]
port = os.environ["POSTGRES_PORT"]
user = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]
dbname = os.environ["POSTGRES_DB"]

deadline = time.monotonic() + 60
while True:
    try:
        with psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=3,
        ):
            break
    except psycopg.OperationalError:
        if time.monotonic() >= deadline:
            print("база не ответила за 60 секунд", file=sys.stderr)
            sys.exit(1)
        time.sleep(1)

print("база готова", flush=True)
PY

# Миграции выполняет только web (RUN_MIGRATIONS=1). Бот переменную не включает.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python /app/src/manage.py migrate --noinput
fi

exec "$@"
