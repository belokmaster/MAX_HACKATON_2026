#!/bin/sh
set -e

# Если директория с сертификатами смонтирована в /app/certs, регистрируем их в системном хранилище
if [ -d /app/certs ] && [ -f /app/certs/Russian_Trusted_Root_CA.cer ]; then
    cp -f /app/certs/*.cer /usr/local/share/ca-certificates/ 2>/dev/null || true
    update-ca-certificates 2>/dev/null || true
fi

exec "$@"
