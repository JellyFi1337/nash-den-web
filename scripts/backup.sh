#!/bin/sh
# Копия базы раз в сутки (14 дней) и архив media раз в неделю.
set -eu

mkdir -p /backups/db /backups/media

run_once() {
    stamp=$(date -u +%Y%m%d-%H%M%S)
    target="/backups/db/nashden-${stamp}.dump"
    pg_dump -Fc -f "$target"
    # Пустой или битый файл не считается копией: метка alive тогда не обновляется.
    if [ ! -s "$target" ]; then
        echo "дамп пустой" >&2
        rm -f "$target"
        exit 1
    fi
    pg_restore --list "$target" >/dev/null
    find /backups/db -name 'nashden-*.dump' -mtime +14 -delete
    if [ ! -f /backups/media/.week ] || [ -n "$(find /backups/media/.week -mtime +6 -print)" ]; then
        tar -czf "/backups/media/media-${stamp}.tar.gz" -C /media .
        date -u +%Y-%m-%dT%H:%M:%SZ > /backups/media/.week
    fi
    date -u +%Y-%m-%dT%H:%M:%SZ > /backups/alive
}

if [ "${BACKUP_ONCE:-0}" = "1" ]; then
    run_once
    exit 0
fi

while true; do
    run_once
    sleep 86400
done
