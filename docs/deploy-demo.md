# Демо на Timeweb Cloud

Один VPS, FastAPI, Caddy и SQLite. Все посетители работают с одним общим кабинетом.
Для начала достаточно Ubuntu 24.04 LTS, 2 vCPU, 2 ГБ RAM, 25–30 ГБ SSD/NVMe
и публичного IPv4 в российском дата-центре. GPU и панель управления не нужны.
Это стартовая конфигурация для нескольких участников демонстрации, без нагрузочного теста.

## 1. Сервер и код

Создайте [VPS/VDS в Timeweb Cloud](https://timeweb.cloud/services/vds-vps), добавьте свой
SSH-ключ. В поле cloud-init загрузите `deploy/cloud-init.yaml`: он установит Docker
из официального репозитория и подготовит `/opt/tinvest-demo`. Выберите чистую
Ubuntu 24.04 LTS без предустановленной панели или другого Docker.
Файл не содержит секретов и не меняет SSH-доступ или firewall.

Подключитесь командой `ssh root@SERVER_IP`, заменив `SERVER_IP` на адрес сервера,
и дождитесь `cloud-init status --wait --long`. Ожидается статус `done` без ошибок;
первоначальная установка может занять несколько минут. Подробности при ошибке:
`/var/log/cloud-init-output.log`.

Если сервер создан без cloud-init, установите Docker Engine и Compose plugin по
[официальной инструкции для Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
Команды ниже выполняются под root; для другого пользователя нужен `sudo` перед Docker.

На сервере:

```bash
mkdir -p /opt/tinvest-demo
docker version
docker compose version
```

С Mac скопируйте только рабочую версию; команда не передаёт `.env`, SQLite, историю
чатов и временные файлы:

```bash
rsync -av --include='.env.deploy.example' --exclude='.env' --exclude='.env.*' --exclude='.git/' \
  --exclude='.venv/' --exclude='__pycache__/' --exclude='*.sqlite3*' \
  --exclude='backups/' \
  /Users/vadimv/code/tinvest-codex/tinvest-redesign-v2/ \
  root@SERVER_IP:/opt/tinvest-demo/
```

## 2. Ключ и пароль

Далее на сервере:

```bash
cd /opt/tinvest-demo
umask 077
cp -n .env.deploy.example .env.deploy
chmod 600 .env.deploy
docker run --rm -it caddy:2-alpine caddy hash-password
nano .env.deploy
```

Введите пароль в интерактивный запрос Caddy. В `.env.deploy` укажите:

- `OPENROUTER_API_KEY` — свой ключ с доступным балансом;
- `DEMO_PASSWORD_HASH` — полученный bcrypt-хеш **в одинарных кавычках**;
- `DEMO_USER` — логин для просмотра, например `demo`;
- `MOCK_LLM=0` — настоящие вызовы модели.

Кавычки сохраняют символы `$` в хеше. Не вставляйте пароль или ключ в команды,
не публикуйте `.env.deploy` и вывод `docker compose config` с секретами.
Конфигурацию можно проверить без вывода её значений через `config --quiet`.

Для показа без модели можно явно установить `MOCK_LLM=1`. При `MOCK_LLM=0`
и пустом ключе контейнер завершится с понятной ошибкой, чтобы отсутствие ключа
не выглядело как успешное подключение модели.

## 3. Проверка OpenRouter с VPS

```bash
docker compose --env-file .env.deploy config --quiet
docker compose --env-file .env.deploy build app
docker compose --env-file .env.deploy run --rm --no-deps app python -m scripts.check_openrouter
```

Последняя команда делает небольшой платный запрос через ту же цепочку structured
outputs, которую использует приложение. При необходимости формата могут быть
несколько попыток. Успех: `OpenRouter OK: ...`; при ошибке код возврата ненулевой.
Ключ, содержимое портфелей и переписка в этот запрос не передаются (кроме ключа
в заголовке авторизации). Скрипт проверяет `FAST_MODEL`; `SMART_MODEL` нужен при
пересборке базы бумаг и для показа с готовой базой не вызывается.

Доступность зависит от IP сервера, ключа, баланса, модели и её провайдера. Если
проверка не прошла, проверьте эти параметры, при необходимости измените `FAST_MODEL`
на доступную вашему ключу модель и повторите. Размещение сайта и SQLite в РФ
не меняет того, что обычные LLM-запросы отправляются во внешний OpenRouter.

## 4. Первый запуск без домена

```bash
docker compose --env-file .env.deploy up -d --wait
docker compose --env-file .env.deploy ps
```

На Mac откройте SSH-туннель и оставьте терминал работающим:

```bash
ssh -N -L 8080:127.0.0.1:8080 root@SERVER_IP
```

Откройте `http://localhost:8080/account` и введите логин и пароль.
HTTP передаётся внутри шифрованного SSH-туннеля. Порт 8080 привязан только к loopback
сервера; FastAPI вообще не публикует порт на хост.

В новой SQLite автоматически появятся два встроенных учебных портфеля. Локальные
портфели и чаты с Mac остаются на Mac; при необходимости их можно перенести отдельно.
Не запускайте `scripts/build_universe.py`: текущая `data/universe.json` уже включена в образ.

Проверка защиты из второго терминала Mac с открытым туннелем:

```bash
curl -o /dev/null -s -w '%{http_code}\n' http://localhost:8080/account
curl -o /dev/null -s -w '%{http_code}\n' http://localhost:8080/api/meta
curl --user demo http://localhost:8080/api/meta
```

Первые два запроса должны вернуть `401`. Последний запрос спросит пароль и вернёт
JSON с `universe.ok=true` и `mock=false`, если подключена модель.

## 5. Публичная ссылка с доменом

Направьте DNS-запись A, например `demo.example.ru`, на IPv4 сервера.
Укажите `DEMO_DOMAIN=demo.example.ru` в `.env.deploy` — без `https://` и пути.
В облачном firewall разрешите входящий TCP на 80 и 443, а SSH оставьте доступным
для своего подключения. Если есть AAAA-запись, она тоже должна вести на этот сервер.

```bash
docker compose --env-file .env.deploy -f compose.yaml -f compose.public.yaml config --quiet
docker compose --env-file .env.deploy -f compose.yaml -f compose.public.yaml up -d --wait
```

Caddy запросит сертификат, затем ссылка будет `https://demo.example.ru/account`.
HTTP перенаправляется на HTTPS; пароль требуется для всех страниц, файлов и API.
Выдача сертификата требует корректного DNS и внешней доступности портов 80/443.
Один и тот же логин даёт доступ к общему кабинету и его изменениям.

После подключения домена **во всех последующих командах управления** используйте
оба `-f compose.yaml -f compose.public.yaml` перед подкомандой (`up`, `exec`, `logs`
и т.д.). Команды ниже показывают базовый вариант без домена.

## 6. Обновление, остановка и резервная копия

База лежит в Docker volume `tinvest-demo_account_data`, сертификаты — в отдельных
volumes Caddy. Обычные `up --build`, `restart` и `down` сохраняют эти данные.
Не используйте `down -v`: этот флаг удаляет volumes вместе с базой.

Перед обновлением создайте согласованный снимок через SQLite backup API, затем
скопируйте его из контейнера:

```bash
mkdir -p backups
chmod 700 backups
docker compose --env-file .env.deploy exec -T app python -c '
import datetime, sqlite3
from pathlib import Path
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
out = Path("/state/backups")
out.mkdir(exist_ok=True)
with sqlite3.connect("/state/account.sqlite3") as src, sqlite3.connect(out / (stamp + ".sqlite3")) as dst:
    src.backup(dst)
print(stamp)
'
docker compose --env-file .env.deploy cp app:/state/backups/. ./backups/
```

Скачайте нужный снимок с сервера отдельно. Бэкап на том же VPS не защищает от его потери.
Для восстановления остановите стек, скопируйте выбранный снимок во временный
контейнер того же образа и в volume `/state` с владельцем `10001:10001`; затем
запустите стек. Восстановление заменяет текущий кабинет, поэтому сначала сохраните
снимок текущего состояния.

После передачи обновлённого кода:

```bash
docker compose --env-file .env.deploy up -d --build --wait
docker compose --env-file .env.deploy logs --tail 100 app web
```

Остановить:

```bash
docker compose --env-file .env.deploy down
```

## Источники настройки

- [Docker Compose: переменные окружения](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/).
- [Caddy: basic_auth и хеширование паролей](https://caddyserver.com/docs/caddyfile/directives/basic_auth).
- [OpenRouter: Chat Completions API](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion).
