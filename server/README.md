# .NET friends service

[English](#english) · [Русский](#русский)

## English

The friends tab of .NET Launcher (requests, online status, invites, "Play together") talks to this service.
It is one Python file with no dependencies (Python 3.10+), it stores data in SQLite, and it never sees passwords:
the launcher proves who a player is the same way a Minecraft server does it, through Ely.by `join` / `hasJoined`.

### Run

```bash
python3 friends_server.py --host 0.0.0.0 --port 8770 --db friends.db
```

Open port 8770 (or put it behind a reverse proxy such as Caddy or nginx with HTTPS, which is recommended:
session tokens travel in the `Authorization` header).

systemd unit example (`/etc/systemd/system/net-friends.service`):

```ini
[Unit]
Description=.NET Launcher friends service
After=network-online.target

[Service]
WorkingDirectory=/opt/net-friends
ExecStart=/usr/bin/python3 /opt/net-friends/friends_server.py --host 127.0.0.1 --port 8770 --db /opt/net-friends/friends.db
Restart=on-failure
User=netfriends

[Install]
WantedBy=multi-user.target
```

Caddy example: `friends.example.net { reverse_proxy 127.0.0.1:8770 }`

### Tell the launchers where it is

Add the address to `catalog.json` in this repository, and every player gets it on the next start:

```json
"friends": {"url": "https://friends.example.net"}
```

A player can also enter it by hand: Settings → Launcher → Friends server.

## Русский

Вкладка «Друзья» в .NET Launcher (заявки, статус «в сети», приглашения, «Играть вместе») работает через эту службу.
Это один файл на Python без зависимостей (Python 3.10+), данные хранятся в SQLite, пароли служба не видит:
лаунчер доказывает, кто игрок, так же, как это делает Minecraft-сервер, через `join` / `hasJoined` Ely.by.

### Запуск

```bash
python3 friends_server.py --host 0.0.0.0 --port 8770 --db friends.db
```

Открой порт 8770 или поставь службу за обратный прокси (Caddy, nginx) с HTTPS. HTTPS лучше: токен сессии
передаётся в заголовке `Authorization`.

Пример службы systemd (`/etc/systemd/system/net-friends.service`) и настройки Caddy — в английской части выше,
они одинаковые.

### Как лаунчеры узнают адрес

Добавь адрес в `catalog.json` этого репозитория, и все игроки получат его при следующем запуске:

```json
"friends": {"url": "https://friends.example.net"}
```

Игрок может вписать адрес и сам: Настройки → Лаунчер → Сервер друзей.

## Cloudflare Workers (free hosting)

`server/cloudflare/` is the same service for Cloudflare Workers + D1 (free plan, no card, does not sleep).

```bash
cd server/cloudflare
npm install
npx wrangler login
npx wrangler d1 create net-friends          # put the printed database_id into wrangler.toml
npx wrangler d1 execute net-friends --remote --file schema.sql
npx wrangler deploy                          # prints https://net-friends.<your-subdomain>.workers.dev
```

Then put that address into `catalog.json` → `"friends": {"url": "…"}`.

Тот же сервис для бесплатного Cloudflare Workers лежит в `server/cloudflare/`, команды выше.
