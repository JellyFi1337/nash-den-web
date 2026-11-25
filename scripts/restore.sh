#!/bin/sh
# Восстанавливает базу из копии pg_dump -Fc и, если указан второй файл, каталог media.
set -eu

dump="${1:-}"
if [ -z "$dump" ]; then
    echo "Укажите файл копии: restore.sh /backups/db/nashden-ГГГГММДД-ЧЧММСС.dump [/backups/media/media-….tar.gz]" >&2
    exit 1
fi

pg_restore --clean --if-exists --no-owner --dbname="${PGDATABASE:?}" "$dump"

media="${2:-}"
if [ -n "$media" ]; then
    tar -xzf "$media" -C /media
fi
