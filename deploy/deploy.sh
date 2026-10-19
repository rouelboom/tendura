#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
SERVER_HOST="${TENDURA_SERVER_HOST:?Задайте TENDURA_SERVER_HOST}"
SERVER_USER="${TENDURA_SERVER_USER:-root}"
REMOTE="${SERVER_USER}@${SERVER_HOST}"
BOT_ROOT=/opt/tendura
ALICE_ROOT=/opt/tendura-alice
BACKUP_ROOT=/opt/tendura-backups
KEEP_RELEASES=10
COMMIT="${GITHUB_SHA:-$(git -C "$PROJECT_DIR" rev-parse HEAD)}"
RELEASE="$BACKUP_ROOT/release-$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT:0:7}"

info() { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR %s\n' "$*" >&2; exit 1; }

# Внутри функций, вызванных через if/||, errexit не действует, поэтому ошибки проверяются явно.
upload() {
  rsync -rlptz --delete --exclude __pycache__ "$PROJECT_DIR/tendura/" "$REMOTE:$BOT_ROOT/tendura/" &&
    rsync -rlptz --delete --exclude __pycache__ "$PROJECT_DIR/tendura/" "$REMOTE:$ALICE_ROOT/tendura/"
}

restart_and_check() {
  ssh "$REMOTE" bash -s <<'REMOTE_SCRIPT'
services=(tendura.service tendura-alice.service)
restarts() {
  for service in "${services[@]}"; do
    systemctl show "$service" -p NRestarts --value || return 1
  done
}
systemctl restart "${services[@]}" || exit 1
before="$(restarts)" || exit 1
# Сервисы перезапускаются при падении; ждём дольше RestartSec, чтобы заметить цикл падений.
sleep 15
for service in "${services[@]}"; do
  systemctl is-active --quiet "$service" || { echo "$service не активен" >&2; exit 1; }
done
after="$(restarts)" || exit 1
[[ "$after" == "$before" ]] || { echo 'Сервис перезапускался после падения' >&2; exit 1; }
/opt/tendura/.venv/bin/python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=5)"
REMOTE_SCRIPT
}

rollback() {
  info "Откат на $RELEASE"
  ssh "$REMOTE" "rsync -a --delete '$RELEASE/bot/' '$BOT_ROOT/tendura/' &&
    rsync -a --delete '$RELEASE/alice/' '$ALICE_ROOT/tendura/'" &&
    restart_and_check || printf 'ERROR сервисы не поднялись после отката\n' >&2
  fail 'Деплой не выполнен'
}

[[ -f "$PROJECT_DIR/tendura/__init__.py" ]] || fail "Не найден пакет tendura в $PROJECT_DIR"

info "Резервная копия $RELEASE"
ssh "$REMOTE" "install -d -m 700 '$RELEASE' && cp -a '$BOT_ROOT/tendura' '$RELEASE/bot' &&
  cp -a '$ALICE_ROOT/tendura' '$RELEASE/alice'"

info "Загрузка кода $COMMIT"
upload || rollback

info 'Перезапуск и проверка сервисов'
restart_and_check || rollback

ssh "$REMOTE" "ls -1d '$BACKUP_ROOT'/release-* | head -n -$KEEP_RELEASES | xargs -r rm -rf"
info "Задеплоен $COMMIT"
