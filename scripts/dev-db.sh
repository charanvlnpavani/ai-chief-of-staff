#!/usr/bin/env bash
# Project-local PostgreSQL cluster for development and tests.
#
# - Data lives outside iCloud-synced folders (default ~/.local/share/personal-os/postgres17).
# - Listens on localhost:55432 only, so it never collides with other local Postgres servers.
# - Local connections need no password (development only; never use this setup in production).
#
# Usage: scripts/dev-db.sh {setup|init|start|stop|status|create-dbs}
set -euo pipefail

PGDATA_DIR="${PERSONAL_OS_PGDATA:-$HOME/.local/share/personal-os/postgres17}"
PORT="${PERSONAL_OS_PGPORT:-55432}"
LOG_FILE="$(dirname "$PGDATA_DIR")/postgres17.log"

is_running() { pg_ctl -D "$PGDATA_DIR" status >/dev/null 2>&1; }

case "${1:-status}" in
  init)
    if [ -f "$PGDATA_DIR/PG_VERSION" ]; then
      echo "cluster already exists at $PGDATA_DIR"
    else
      mkdir -p "$(dirname "$PGDATA_DIR")"
      initdb -D "$PGDATA_DIR" --auth-local=trust --auth-host=trust \
        --encoding=UTF8 --locale=C --no-instructions >/dev/null
      printf "\n# personal-os dev cluster\nlisten_addresses = 'localhost'\nport = %s\n" "$PORT" \
        >> "$PGDATA_DIR/postgresql.conf"
      echo "initialised cluster at $PGDATA_DIR (port $PORT)"
    fi
    ;;
  start)
    if is_running; then echo "already running on port $PORT"; else
      pg_ctl -D "$PGDATA_DIR" -l "$LOG_FILE" -w start >/dev/null && echo "started on port $PORT"
    fi
    ;;
  stop)
    if is_running; then pg_ctl -D "$PGDATA_DIR" -w stop >/dev/null && echo "stopped"; else echo "not running"; fi
    ;;
  status)
    if is_running; then echo "running on port $PORT ($PGDATA_DIR)"; else echo "not running"; fi
    ;;
  create-dbs)
    for db in personal_os personal_os_test; do
      if createdb -w -h localhost -p "$PORT" "$db" 2>/dev/null; then echo "created $db"; else echo "$db already exists"; fi
    done
    ;;
  setup)
    "$0" init
    "$0" start
    "$0" create-dbs
    ;;
  *)
    echo "usage: $0 {setup|init|start|stop|status|create-dbs}" >&2
    exit 2
    ;;
esac
