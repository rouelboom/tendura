# Tendura

Telegram-бот для чтения тренировок Training Endurance и отправки отчёта спортсмена.

## Локальный запуск

```bash
cp .env.example .env
UV_PROJECT_ENVIRONMENT=.venv uv sync --python 3.13.9 --no-dev
set -a; source .env; set +a
.venv/bin/python -m tendura
```

Бот поддерживает `/today`, `/tomorrow`, `/week`, `/comment текст`, `/confirm` и `/cancel`.

`/comment` подготавливает отчёт для единственной тренировки на сегодня. Перед записью бот показывает текст и требует `/confirm`; существующий отчёт будет явно отмечен как перезаписываемый.

## Секреты

Не добавляйте `.env`, токен Telegram и cookie Training Endurance в Git. Для cookie используйте полный заголовок `Cookie` успешного запроса Training Endurance, содержащий `ory_kratos_session`.

## Развёртывание

Сервис использует `/opt/tendura`, конфигурацию `/etc/tendura/tendura.env` с правами `600` и unit-файл `deploy/tendura.service`.
