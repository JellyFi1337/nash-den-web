#!/usr/bin/env bash
# Обновление на сервере одной командой: свежий код, копия базы, сборка, перезапуск, проверка.
# Запуск из любого места: bash /opt/nash-den/scripts/update.sh
# С Windows: .\dev.ps1 deploy (docs/DEPLOY.md, раздел 10).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "Нет файла .env рядом с compose.yaml (docs/DEPLOY.md, раздел 7)." >&2
    exit 1
fi
if ! grep -q '^COMPOSE_FILE=' .env; then
    echo "В .env нет строки COMPOSE_FILE: без неё поднимется стек разработки (раздел 7)." >&2
    exit 1
fi

before=$(git rev-parse --short HEAD)
git pull --ff-only --quiet
after=$(git rev-parse --short HEAD)
if [ "$before" = "$after" ]; then
    echo "Код: без изменений ($after)."
else
    echo "Код: $before -> $after"
    git log --oneline "$before..$after" | head -20
fi

# Копия перед обновлением, если стек уже работает. Схему меняют миграции при старте сайта.
if docker compose ps --status running --services 2>/dev/null | grep -qx backup; then
    echo "Копия базы перед обновлением..."
    docker compose exec -T -e BACKUP_ONCE=1 backup /bin/sh /usr/local/bin/backup.sh
fi

docker compose build --pull
docker compose up -d --wait --remove-orphans

# Smoke не создаёт код дня. Если кода сегодня ещё нет, он скажет об этом, а не сломает обновление.
if ! docker compose exec -T web python /app/scripts/smoke.py --base http://127.0.0.1:8000; then
    echo "Smoke не прошёл: посмотрите docker compose logs --tail 200 web" >&2
fi

docker image prune -f >/dev/null
docker compose ps
df -h / | tail -1
