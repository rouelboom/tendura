# Tendura

Telegram-бот для чтения тренировок Training Endurance и отправки отчёта спортсмена.

## Локальный запуск

```bash
cp .env.example .env
UV_PROJECT_ENVIRONMENT=.venv uv sync --python 3.13.9 --no-dev
set -a; source .env; set +a
.venv/bin/python -m tendura
```

Нажмите `/` в Telegram, чтобы открыть меню команд. Основные команды:

- `/today`, `/tomorrow`, `/week` — показать тренировки;
- `/comment_coros` — подготовить голосовой отчёт последней тренировки COROS к записи в Training Endurance;
- `/comment текст`, `/confirm`, `/cancel`, `/edit` — подготовить, подтвердить, отменить или изменить отчёт Training Endurance.

Короткие алиасы: `/t`, `/tm`, `/w`, `/cc`, `/c`, `/ok`, `/x`, `/e`. Старый вариант `/comment-coros` также поддерживается, но Telegram не позволяет добавить команду с дефисом в нативное меню.

`/comment` подготавливает отчёт для единственной тренировки на сегодня. COROS-команды подставляют в тот же сценарий `Workout Note` с часов. Перед записью бот показывает текст и требует `/confirm`; `/edit` ожидает следующее обычное текстовое сообщение и заново показывает предварительный просмотр.

## Секреты

Не добавляйте `.env`, токен Telegram, cookie Training Endurance и `data/coros-oauth.json` в Git. Для cookie используйте полный заголовок `Cookie` успешного запроса Training Endurance, содержащий `ory_kratos_session`. OAuth-файл COROS должен иметь права `600`; его путь задаётся через `TENDURA_COROS_OAUTH_FILE`.

## Развёртывание

Сервис использует `/opt/tendura`, конфигурацию `/etc/tendura/tendura.env`, OAuth-файл `/etc/tendura/coros-oauth.json` с правами `600` и unit-файл `deploy/tendura.service`.
