# Приватный навык Алисы

## Контракт

- Имя навыка: `Тренировочный помощник`.
- Тип: обычный приватный навык Алисы.
- Backend: отдельный процесс `python -m tendura.alice.server` на существующем
  сервере Tendura за nginx.
- Публичный webhook: `https://138-16-161-115.sslip.io/alice`.
- Yandex Cloud Function не используется, чтобы не привязывать платёжный аккаунт
  и исключить облачные списания.

Интенты и гарантированные команды перечислены в `manifest.json`. Текст каждого файла из `intents/` нужно перенести в одноимённый интент в консоли Яндекс Диалогов.

Навык общего типа гарантированно запускается с активационным именем. Короткие варианты без «спроси у Тренировочного помощника» проверяются отдельно на реальной Станции и не считаются гарантированным контрактом платформы.

## Переменные окружения

- `TENDURA_ALICE_SKILL_ID`;
- `TENDURA_ALLOWED_YANDEX_USER_ID`;
- `TENDURA_TRAINING_ENDURANCE_USER_ID`;
- одна из `TENDURA_TRAINING_ENDURANCE_SESSION` или `TENDURA_TRAINING_ENDURANCE_COOKIE`;
- `TENDURA_TIMEZONE`, по умолчанию `Europe/Moscow`.
- `TENDURA_ALICE_HOST`, по умолчанию `127.0.0.1`;
- `TENDURA_ALICE_PORT`, по умолчанию `8081`.

Значения не добавляются в Git и не должны попадать в логи процесса.

## Локальная проверка

Из корня репозитория:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_alice_*.py' -v
TENDURA_ALICE_SKILL_ID=test \
TENDURA_ALLOWED_YANDEX_USER_ID=test \
TENDURA_TRAINING_ENDURANCE_SESSION=test \
TENDURA_TRAINING_ENDURANCE_USER_ID=test \
.venv/bin/python -m tendura.alice.server
```

Проверка доступности локального процесса: `curl http://127.0.0.1:8081/healthz`.
HTTP-сервер не пишет тела запросов и ответов в access-лог.

## Развёртывание на существующем сервере

1. Установить `deploy/alice/tendura-alice.service` как отдельный systemd unit.
   Он использует ту же защищённую конфигурацию `/etc/tendura/tendura.env`, но
   запускает независимый Alice entrypoint.
2. Установить `deploy/alice/nginx.conf`. Backend слушает только localhost;
   наружу публикуются `/alice` и обезличенный `/healthz`.
3. Получить бесплатный сертификат Let's Encrypt для
   `138-16-161-115.sslip.io` и включить его автоматическое продление.
4. Проверить `https://138-16-161-115.sslip.io/healthz`, затем использовать
   `https://138-16-161-115.sslip.io/alice` как webhook навыка.

`sslip.io` бесплатно разрешает имя с IP-адресом сервера. Новая платная
инфраструктура и платёжный аккаунт Yandex Cloud не требуются.

## Настройка приватного навыка

1. Создать в Яндекс Диалогах обычный приватный навык «Тренировочный помощник» и
   указать HTTPS webhook существующего сервера.
2. Добавить перечисленные выше переменные в защищённый EnvironmentFile. Не
   записывать их в исходный код или открытые логи.
3. Создать три интента из `manifest.json`, перенеся грамматики из `intents/`.
4. Первый запрос выполнить в тестовой консоли Диалогов, получить
   `session.user.user_id` из запроса и сохранить его как
   `TENDURA_ALLOWED_YANDEX_USER_ID`. Сам идентификатор не публиковать.
5. Проверить гарантированные команды с активационным именем из `manifest.json`.
   Короткие фразы без имени навыка считаются экспериментальными до проверки на
   реальной Станции.

## Отзыв доступа

Отключить или удалить приватный навык, остановить `tendura-alice.service` и
удалить nginx location. Если cookie или session Training Endurance могли стать
доступны третьим лицам, завершить сессию в Training Endurance и заменить секрет
в конфигурации Telegram-сервиса.
