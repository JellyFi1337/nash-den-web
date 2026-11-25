# Запуск на сервере

Инструкция с нуля: чистый сервер Ubuntu 24.04, рабочий компьютер на Windows 11, приватный репозиторий на GitHub. Основной режим этой версии — **без SSL**: сайт открывается по `http://IP-сервера`, бот работает только в личных сообщениях и в группу не добавляется. Переход на HTTPS, когда появится домен, — раздел 12.

Сайт, бот, база, копии и Caddy работают в Docker. Наружу открыт только порт 80 (и SSH). База и сам сайт снаружи не видны.

Обозначения в примерах:

- `203.0.113.10` — IP вашего сервера (замените на свой);
- `deploy` — пользователь на сервере, под которым всё работает;
- `nashden` — короткое имя сервера в SSH на вашем компьютере;
- `/opt/nash-den` — каталог проекта на сервере;
- `ВЛАДЕЛЕЦ/nash-den` — ваш приватный репозиторий на GitHub.

Команды в блоках `powershell` выполняются на Windows, в блоках `bash` — на сервере.

## 0. Что понадобится

- Сервер (VPS) с Ubuntu 24.04: от 2 ГБ памяти и 20 ГБ диска. При 1 ГБ сборка образа упрётся в память — тогда обязательно файл подкачки (раздел 3).
- Доступ root к серверу: пароль или ключ от хостинга.
- Ваш аккаунт GitHub с доступом к репозиторию.
- На Windows 11 уже есть клиент OpenSSH (`ssh`, `scp`, `ssh-keygen`). Проверка: `ssh -V`.

## 1. Ключ SSH на Windows 11

Один ключ на рабочий компьютер. Пароль на ключ (passphrase) лучше задать: украденный файл без пароля — это доступ к серверу.

```powershell
ssh-keygen -t ed25519 -C "work-pc"
```

Нажмите Enter на вопрос о пути — ключ ляжет в `C:\Users\<вы>\.ssh\id_ed25519`, открытая часть — в `id_ed25519.pub`.

Агент нужен только если у ключа есть пароль: он запоминает пароль до перезагрузки. Без пароля этот шаг пропустите.

Включение агента — один раз, в PowerShell **от администратора**: «Пуск» → наберите `PowerShell` → правой кнопкой → «Запуск от имени администратора». В обычном окне Windows ответит «Отказано в доступе»: служба `ssh-agent` по умолчанию отключена, и включить её может только администратор. Тогда и `ssh-add` пишет `Error connecting to agent: No such file or directory`.

```powershell
Get-Service ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
```

Затем в обычном PowerShell:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

Короткое имя сервера. Откройте (или создайте) файл `C:\Users\<вы>\.ssh\config` в Блокноте и добавьте:

```text
Host nashden
    HostName 203.0.113.10
    User deploy
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
```

Пока пользователя `deploy` нет, входите как root: `ssh root@203.0.113.10`.

Если хостинг при создании сервера предлагает вставить открытый ключ — вставьте содержимое `id_ed25519.pub`, и root будет входить по ключу. Если нет, передайте ключ сами (спросит пароль root один раз):

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@203.0.113.10 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Проверка: `ssh root@203.0.113.10` входит без пароля root (может спросить пароль ключа, если агент не запущен).

## 2. Первичная настройка Ubuntu

Войдите как root:

```powershell
ssh root@203.0.113.10
```

Команды этого раздела выполняются под root, поэтому без `sudo`.

### 2.1. Имя сервера

Некоторые хостинги не прописывают имя сервера в `/etc/hosts`. Тогда каждая команда `sudo` печатает `sudo: unable to resolve host …: Name or service not known` и заметно задумывается. Проверка и исправление:

```bash
hostname
grep -q "$(hostname)" /etc/hosts || echo "127.0.1.1 $(hostname)" >> /etc/hosts
sudo true
```

После этого `sudo true` ничего не печатает. Если после перезагрузки сообщение вернулось, `/etc/hosts` перезаписывает cloud-init: добавьте ту же строку в `/etc/cloud/templates/hosts.debian.tmpl` или отключите `manage_etc_hosts` в `/etc/cloud/cloud.cfg`.

### 2.2. Обновления и пакеты

```bash
apt-get update && apt-get -y full-upgrade
apt-get install -y git ufw ca-certificates curl unattended-upgrades
timedatectl set-timezone Europe/Moscow
dpkg-reconfigure -f noninteractive unattended-upgrades
```

Если `full-upgrade` обновил ядро, перезагрузите сервер (`reboot`) и войдите снова как root.

### 2.3. Пользователь deploy и его ключ

```bash
adduser --gecos "" deploy
usermod -aG sudo deploy
```

`adduser` спросит пароль — он нужен для `sudo`. По SSH с ним войти будет нельзя (раздел 2.5).

Ключ для входа. Если root входит по ключу, у него есть файл `/root/.ssh/authorized_keys` — скопируйте его:

```bash
ls -l /root/.ssh/authorized_keys
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -m 600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
```

Если `ls` ответил `No such file or directory` (root входил по паролю), вставьте ключ сами. На Windows покажите его:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

Скопируйте одну строку `ssh-ed25519 AAAA… work-pc` и на сервере:

```bash
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo "ssh-ed25519 AAAA… work-pc" >> /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

Проверка на сервере — в файле есть ваша строка, владелец `deploy`, права `-rw-------`:

```bash
ls -l /home/deploy/.ssh/authorized_keys
cat /home/deploy/.ssh/authorized_keys
```

### 2.4. Проверка входа — обязательно до закрытия паролей

**Окно с root не закрывайте.** Откройте второе окно PowerShell и войдите как `deploy`:

```powershell
ssh nashden
```

Уже на сервере, в этом втором окне:

```bash
whoami
sudo whoami
```

Должно ответить `deploy`, затем (после пароля `deploy`) — `root`. Пока это не получилось, к разделу 2.5 не переходите: после него войти можно будет только по ключу.

Если `ssh nashden` пишет `Permission denied (publickey)` — ключ в `authorized_keys` не тот или не те права (раздел 2.3). `ssh -v nashden` покажет, какой ключ предлагается.

### 2.5. Вход только по ключу

Только после успешной проверки, в окне root:

```bash
cat > /etc/ssh/sshd_config.d/10-nashden.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sshd -t && systemctl restart ssh
```

Файл с номером `10-` читается раньше `50-cloud-init.conf`, который ставят некоторые хостинги, поэтому выигрывает он. Порт SSH не меняйте: в Ubuntu 24.04 он задаётся через `ssh.socket`, и ошибка там отрежет доступ.

Ещё раз из **нового** окна PowerShell: `ssh nashden` входит, а `ssh root@203.0.113.10` отвечает `Permission denied`. Только теперь окно root можно закрыть.

### 2.6. Если вход закрылся

Вход по паролю и вход root уже выключены, а `ssh nashden` не пускает:

- Окно root ещё открыто — верните ключ по разделу 2.3 и проверьте по 2.4. Либо временно откатите запрет: `rm /etc/ssh/sshd_config.d/10-nashden.conf && systemctl restart ssh`.
- Все окна закрыты — откройте консоль сервера в панели хостинга (VNC, «Консоль», «Emergency console»). Войдите там как root с паролем: консоль не зависит от настроек SSH. Вставка из буфера в такой консоли обычно не работает, поэтому ключ вручную не набирайте, а временно верните вход по паролю:

  ```bash
  rm /etc/ssh/sshd_config.d/10-nashden.conf
  systemctl restart ssh
  ```

  Затем с Windows передайте ключ пользователю `deploy` (спросит пароль `deploy`):

  ```powershell
  type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh deploy@203.0.113.10 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
  ```

  Проверьте вход по разделу 2.4 и снова закройте пароли по разделу 2.5.

Признак этого состояния: `ssh root@…` отвечает `Permission denied (publickey)` — это значит, что раздел 2.5 уже применён, и root по SSH больше не пускают. Так и должно быть; ключ нужен пользователю `deploy`.

Дальше всё делается под `deploy`, через `ssh nashden`.

## 3. Брандмауэр и подкачка

Разделы 3 и 4 можно выполнять и под root — `sudo` там просто ничего не меняет. К пользователю привязана только одна команда, `usermod -aG docker deploy` в конце раздела 4.

Открыты только SSH и HTTP:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw enable
sudo ufw status
```

Docker публикует порты в обход `ufw`. Поэтому важно, что в рабочем режиме наружу публикуется только порт 80 у Caddy: база и сайт портов на хост не открывают (раздел 7, строка `COMPOSE_FILE`).

Если памяти 1–2 ГБ, добавьте подкачку 2 ГБ:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## 4. Docker

Официальный репозиторий Docker:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Ограничение журналов контейнеров, иначе за месяцы они займут диск:

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

Право вызывать Docker без `sudo`:

```bash
sudo usermod -aG docker deploy
```

Выйдите (`exit`) и войдите снова (`ssh nashden`) — группа начинает действовать после нового входа. Проверка:

```bash
docker run --rm hello-world
docker compose version
```

Нужна версия Compose 2.24 или новее (в файлах используется `!override`).

## 5. Приватный репозиторий: ключ развёртывания

Сервер получает код по отдельному ключу только для чтения (Deploy key). Ваш личный ключ GitHub на сервер не кладётся.

На сервере:

```bash
ssh-keygen -t ed25519 -C "nash-den-server" -f ~/.ssh/nashden_deploy -N ""
cat ~/.ssh/nashden_deploy.pub
```

Скопируйте выведенную строку. На GitHub: репозиторий → **Settings** → **Deploy keys** → **Add deploy key**. Название — `server`, ключ — эта строка, галочку **Allow write access не ставьте**.

Привязка ключа к GitHub на сервере:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github-nashden
    HostName github.com
    User git
    IdentityFile ~/.ssh/nashden_deploy
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T github-nashden
```

При первом подключении SSH покажет отпечаток GitHub. Для ключа ED25519 он должен быть `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` (сверьте со страницей GitHub «GitHub's SSH key fingerprints»). Ответ `successfully authenticated` значит, что ключ подошёл.

`Permission denied (publickey)` на этом шаге значит, что ключ ещё не добавлен в **Deploy keys** именно этого репозитория. Добавьте его и повторите `ssh -T github-nashden`. Блок `Host github-nashden` дописывайте в `~/.ssh/config` один раз; если повторили, удалите лишнюю копию (`nano ~/.ssh/config`).

Клонирование. В адресе вместо `github.com` стоит псевдоним `github-nashden` — только через него SSH берёт ключ развёртывания. Адрес `git@github.com:…`, скопированный со страницы GitHub, ответит `Permission denied (publickey)`.

```bash
sudo mkdir -p /opt/nash-den
sudo chown deploy:deploy /opt/nash-den
git clone git@github-nashden:ВЛАДЕЛЕЦ/nash-den.git /opt/nash-den
cd /opt/nash-den
git log --oneline -3
```

Сервер только читает репозиторий. Правки делаются на Windows, отправляются в GitHub (`git push`), и сервер забирает их обновлением (раздел 10).

## 6. Папка private

Настоящие данные команды в git не входят: `private/team.json`, `private/reports/*.json`, `private/schedule.json` (и `private/chats.toml`, если бот когда-нибудь будет в группе). Подробно — `docs/INITIAL_DATA.md`.

С Windows, из каталога проекта:

```powershell
.\dev.ps1 private
```

Команда копирует папку `private` на сервер (`scp`) и перечитывает расписание. Первый раз сайт ещё не запущен, поэтому вторая часть скажет, что расписание не перечитано, — это нормально, его загрузит раздел 9. То же вручную:

```powershell
scp -r .\private nashden:/opt/nash-den/
```

Контейнеры видят папку только для чтения как `/app/private`.

## 7. Файл .env

`.env.example` — образец **для компьютера разработчика**. Скопированный без правок, он поднимает стек разработки: без Caddy, сайт только на `127.0.0.1:8000`, снаружи порт 80 закрыт. Поэтому на сервере файл проще сразу записать целиком. Подставьте свой IP в первой строке и выполните блок целиком; секрет, пароль базы и путь админки сгенерируются сами:

```bash
cd /opt/nash-den
IP=203.0.113.10
cat > .env <<EOF
COMPOSE_FILE=compose.yaml:compose.prod.yaml:compose.http.yaml
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
DJANGO_ALLOWED_HOSTS=$IP
DJANGO_CSRF_TRUSTED_ORIGINS=http://$IP
DJANGO_ADMIN_PATH=kabinet-$(python3 -c "import secrets; print(secrets.token_hex(3))")/
POSTGRES_DB=nashden
POSTGRES_USER=nashden
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(24))")
POSTGRES_HOST=db
POSTGRES_PORT=5432
SITE_URL=http://$IP
SITE_DOMAIN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_OWNER_ID=
CHATS_CONFIG=/app/private/chats.toml
SHEET_URL=
SHEET_TTL=900
SHEET_TIMEOUT=10
TRUSTED_PROXY_COUNT=1
DJANGO_SECURE_COOKIES=0
DJANGO_HSTS_SECONDS=0
DJANGO_HSTS_INCLUDE_SUBDOMAINS=0
DJANGO_HSTS_PRELOAD=0
ACME_EMAIL=
TZ=Europe/Moscow
EOF
chmod 600 .env
nano .env
```

В `nano` впишите `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_OWNER_ID` и `SHEET_URL`, сохраните (Ctrl+O, Enter) и выйдите (Ctrl+X). Путь админки: `grep ADMIN_PATH .env`.

Если до этого стек уже поднимался со старым `.env` (в `docker compose ps` есть `127.0.0.1:5432` и нет `caddy`), сначала убедитесь, что база действительно пустая и том создан вами только для этого запуска. Лишь тогда снимите его: `docker compose down -v`; базу с данными не удаляйте, согласуйте пароль PostgreSQL с настройками. Иначе том базы останется со старым паролем, и сайт не подключится.

Отдельно сгенерировать случайные значения:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
python3 -c "import secrets; print(secrets.token_hex(24))"
```

Значения для режима без SSL:

| Переменная | Что поставить |
|---|---|
| `COMPOSE_FILE` | `compose.yaml:compose.prod.yaml:compose.http.yaml` — **обязательно**, в образце строка закомментирована: уберите `#`. С ней все команды — просто `docker compose …`. Без неё поднимется стек разработки с открытой базой |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | первая случайная строка. Не теряйте и не меняйте: иначе все входы сбросятся |
| `DJANGO_ALLOWED_HOSTS` | `203.0.113.10` (и домен через запятую, если он уже смотрит на сервер). `127.0.0.1` и `localhost` сайт добавляет сам — для проверки здоровья |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://203.0.113.10` |
| `DJANGO_ADMIN_PATH` | свой путь админки, не `admin/`, например `kabinet-7f3/` |
| `POSTGRES_DB`, `POSTGRES_USER` | `nashden` |
| `POSTGRES_PASSWORD` | вторая случайная строка. Применяется только при первом создании тома базы |
| `POSTGRES_HOST`, `POSTGRES_PORT` | `db`, `5432` |
| `SITE_URL` | `http://203.0.113.10` — этот адрес бот присылает вместе с кодом |
| `SITE_DOMAIN` | пусто. Нужен только для HTTPS |
| `TELEGRAM_BOT_TOKEN` | токен рабочего бота из BotFather (раздел 8) |
| `TELEGRAM_BOT_USERNAME` | имя бота без `@` |
| `TELEGRAM_OWNER_ID` | ваш числовой идентификатор Telegram (`@userinfobot`) |
| `CHATS_CONFIG` | `/app/private/chats.toml`. Файла может не быть: без группы он не нужен |
| `SHEET_URL` | ссылка на таблицу команды (только чтение, `docs/SHEET.md`) |
| `SHEET_TTL`, `SHEET_TIMEOUT` | `900`, `10` |
| `TRUSTED_PROXY_COUNT` | `1` |
| `DJANGO_SECURE_COOKIES` | `0`. По HTTP cookie с флагом Secure браузер не вернёт, и вход не заработает |
| `DJANGO_HSTS_SECONDS` | `0` |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD` | `0` |
| `ACME_EMAIL` | пусто |
| `TZ` | `Europe/Moscow` |

`compose.http.yaml` всё равно выставляет `DJANGO_SECURE_COOKIES=0` и `DJANGO_HSTS_SECONDS=0`, а Caddy в этом режиме сертификаты не запрашивает и слушает только порт 80.

## 8. Бот в BotFather — только личка

Нужен отдельный рабочий бот, не тестовый. Название и тексты — `docs/BOT_SETUP.md`.

1. `@BotFather` → `/newbot` → название и имя. Токен впишите в `.env`.
2. `/setjoingroups` → **Disable**: бот не нужен в группах, и его туда не добавят.
3. `/setdescription`, `/setabouttext`, `/setuserpic` — по `docs/BOT_SETUP.md`.
4. `/setcommands`: `start - начать и получить код дня` и `code - код дня`.
5. Режим приватности (`/setprivacy`) в этом режиме не важен: бот читает только личку.

Бот выдаёт код дня в ответ на `/start`, `/code` или любое сообщение в личке — тем, кто есть в составе команды. Связь — по имени пользователя Telegram в `private/team.json` или в карточке человека в админке. Утренней рассылки нет (её включает `CODE_BROADCAST=1`). Кто и сколько раз брал код — `/visits` в вашей личке и «Обращения к боту» в админке.

По адресу `http://` кнопка меню «Открыть сайт» и вход из Telegram не работают — их Telegram разрешает только для `https://`. Адрес сайта приходит ссылкой в сообщении с кодом, кнопки под сообщением нет.

## 9. Первый запуск

```bash
cd /opt/nash-den
docker compose up -d --build --wait
docker compose ps
```

Сборка занимает несколько минут. Все сервисы — `healthy`: `db`, `web`, `bot`, `caddy`, `backup`. Сайт при старте сам применяет миграции, бот ждёт, пока сайт станет здоровым.

Данные команды. Первый раз база пустая, число подтверждения не нужно:

```bash
docker compose exec web python /app/src/manage.py load_private --reset --reports --force
docker compose exec web python /app/src/manage.py load_schedule
docker compose exec web python /app/src/manage.py sync_sheet
```

Администратор сайта:

```bash
docker compose exec web python /app/src/manage.py createsuperuser
```

Проверка:

```bash
docker compose exec web python /app/scripts/smoke.py --base http://127.0.0.1:8000
```

Откройте в браузере `http://203.0.113.10` — сайт просит код дня. Код придёт в личку бота после «Начать»; владельцу его покажет и команда `docker compose exec web python /app/src/manage.py daycode`. Админка — `http://203.0.113.10/<DJANGO_ADMIN_PATH>`.

`manage.py check --deploy` в этом режиме предупреждает про Secure у cookie и HSTS (W004, W012, W016). Это ожидаемо для HTTP и пропадает после перехода на HTTPS.

Повторная загрузка `load_private --reset` на работающем сервере стирает сообщения и отчёты, которых нет в `private/reports`. Команда без числа только печатает сводку; повтор с `--confirm-delete=ЧИСЛО` сначала пишет копию `before-reset-….dump`, потом загружает. Подробно — `docs/OPERATIONS.md` и PLAN A4.1 «Режимы данных».

## 10. Обновление

Обычный путь — с Windows, после `git push` в GitHub:

```powershell
.\dev.ps1 deploy
```

Команда заходит на сервер `nashden` по SSH и запускает `scripts/update.sh`. Другой псевдоним или каталог: `.\dev.ps1 deploy myserver /srv/nash-den`. На Linux то же — `make deploy`.

То же на самом сервере:

```bash
bash /opt/nash-den/scripts/update.sh
```

Что делает скрипт по шагам:

1. Проверяет, что в `.env` есть `COMPOSE_FILE`.
2. `git pull --ff-only` и печатает новые коммиты. Если на сервере кто-то правил файлы руками, pull остановится — правьте только через git.
3. Делает копию базы, если стек уже работает.
4. Собирает образы (`--pull` подтягивает обновления базовых образов) и перезапускает (`up -d --wait`). Миграции применяются при старте сайта.
5. Запускает smoke. Он не создаёт код дня; если кода на сегодня ещё нет, скажет об этом и обновление не сорвёт.
6. Удаляет старые образы и показывает место на диске.

Новые данные (`private/`) — отдельно: `.\dev.ps1 private`. Расписание при этом перечитывается само, а состав и отчёты — только командой из раздела 9.

### Откат

```bash
cd /opt/nash-den
git log --oneline -10
git checkout <прежний коммит>
docker compose up -d --build --wait
```

Вернуться на основную ветку: `git checkout main`. Если новая миграция уже изменила базу и старый код с ней не работает, сначала восстановите копию (раздел 11).

## 11. Журналы, копии, восстановление

Журналы (хвост и выход):

```bash
docker compose logs --tail 200
docker compose logs --tail 200 web
docker compose logs --tail 200 bot
docker compose logs --tail 200 caddy
```

Токен бота в журнал не пишется.

Сервис `backup` пишет копию базы при старте и затем раз в сутки (хранятся 14 дней), архив фото — раз в неделю. Всё лежит в томе `backup_data`:

```bash
docker compose exec backup ls -1 /backups/db /backups/media
```

Копия вручную:

```bash
docker compose exec -T -e BACKUP_ONCE=1 backup /bin/sh /usr/local/bin/backup.sh
```

Восстановление. Остановите сайт и бота, чтобы они не писали в базу:

```bash
docker compose stop web bot
docker compose exec backup /bin/sh /usr/local/bin/restore.sh /backups/db/nashden-ФАЙЛ.dump /backups/media/media-ФАЙЛ.tar.gz
docker compose start web bot
```

Второй аргумент можно не указывать, если фото восстанавливать не нужно. `restore.sh` заменяет текущую базу содержимым копии.

Копии лежат на том же диске, что и база. Раз в месяц заберите свежую на Windows:

```powershell
ssh nashden "cd /opt/nash-den && docker compose cp backup:/backups/db/nashden-ФАЙЛ.dump /tmp/nashden.dump"
scp nashden:/tmp/nashden.dump .\nashden.dump
ssh nashden "rm /tmp/nashden.dump"
```

Файл копии содержит личные данные команды: храните его вне репозитория и вне общих папок.

### Обслуживание без бота

Пока бот работает, он сам читает таблицу раз в час и чистит старые сессии. Если бот выключен, то же делает задание cron пользователя `deploy` (`crontab -e`); таблица и тогда читается не чаще раза в час:

```cron
*/15 * * * * cd /opt/nash-den && docker compose exec -T web python /app/src/manage.py maintain
```

## 12. Переход на HTTPS

HTTP — временный режим, решение владельца (DECISIONS 043). Код дня и cookie входа идут по сети открытым текстом: в чужом Wi-Fi их можно перехватить. Защита — смена кода в 05:00 и сброс всех входов. Как только появится домен, переходите на HTTPS.

1. У регистратора домена запись A указывает на `203.0.113.10`. Проверка с Windows: `nslookup den.example`.
2. На сервере: `sudo ufw allow 443/tcp`.
3. В `.env`:
   - `COMPOSE_FILE=compose.yaml:compose.prod.yaml` (без `compose.http.yaml`);
   - `SITE_DOMAIN=den.example`;
   - `DJANGO_ALLOWED_HOSTS=den.example`;
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://den.example`;
   - `SITE_URL=https://den.example`;
   - `DJANGO_SECURE_COOKIES=1`, `DJANGO_HSTS_SECONDS=31536000` (их всё равно выставляет `compose.prod.yaml`).
4. `docker compose up -d --wait`. Caddy сам получит сертификат Let's Encrypt за минуту-две (`docker compose logs --tail 50 caddy`).
5. Проверка: `docker compose exec web python /app/scripts/smoke.py --base https://den.example` — для `https://` он проверяет ещё сертификат, переход с HTTP, `Secure` у cookie и HSTS.

После перехода у бота появляется кнопка меню «Открыть сайт», а сайт открывается внутри Telegram. Все входы один раз сбросятся (cookie станут Secure) — участники вводят код заново.

`DJANGO_HSTS_INCLUDE_SUBDOMAINS` и `DJANGO_HSTS_PRELOAD` оставьте `0`, пока не убедитесь, что все нужные имена этого домена открываются по HTTPS. Preload потом нельзя быстро отменить.

### HTTPS без купленного домена

- **Бесплатный поддомен динамического DNS.** Сервис выдаёт имя вида `команда.пример.dyn.example` и ведёт его на ваш IP. Дальше всё как выше, с этим именем. `HSTS_PRELOAD` и `HSTS_INCLUDE_SUBDOMAINS` держите `0`: домен чужой.
- **Сертификат на IP.** Let's Encrypt выдаёт короткие (около шести дней) сертификаты на IP в профиле `shortlived` с 15.01.2026 (https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability). Что образ `caddy:2.11.4` получает такой сертификат, на этом сервере не проверялось (заявка Caddy 7399). Экспериментально.
- **Частная сеть (VPN).** Сайт виден только участникам сети. Нужен доверенный сертификат внутри неё; самоподписанный для команды не годится.

## 13. Проверка на Windows без сервера

Отдельный проект nashden-localprod, собственные новые тома. Правила изоляции — PLAN A5. До запуска проверьте docker compose ls и docker volume ls: если имя уже использовалось, прежние тома сохраняются; не заполняйте и не удаляйте их как временные.

Создайте вне репозитория override с собственным тегом образа и отключёнными внешними источниками:

```yaml
services:
  web:
    image: nashden-web-check
    environment:
      TELEGRAM_BOT_TOKEN: ""
      TELEGRAM_BOT_USERNAME: ""
      TELEGRAM_OWNER_ID: ""
      CODE_BROADCAST: "0"
      CHATS_CONFIG: /app/no-chats.toml
      SHEET_URL: ""
  bot:
    profiles: ["never"]
```

Если прежние тома этого проекта существуют, используйте новый отдельный проект для проверки. Относительные пути берутся от первого compose.yaml. Ниже <override> — абсолютный путь к временному файлу:

```powershell
docker compose -p nashden-localprod -f compose.yaml -f compose.local-prod.yaml -f "<override>" up -d --build --wait db web caddy
docker compose -p nashden-localprod -f compose.yaml -f compose.local-prod.yaml -f "<override>" exec web python /app/src/manage.py seed_demo --reset --force
docker compose -p nashden-localprod -f compose.yaml -f compose.local-prod.yaml -f "<override>" exec web python /app/src/manage.py daycode > $null
docker compose -p nashden-localprod -f compose.yaml -f compose.local-prod.yaml -f "<override>" exec web python /app/scripts/smoke.py --base http://127.0.0.1:8000
```

daycode нужен только в этой отдельной проверочной базе: smoke сам код не создаёт. С Windows сайт открыт http://127.0.0.1:8080. Для настоящего режима отдельной базы — load_private --reset --reports --force, без sync_sheet; проверьте правила подтверждения и источники. Для manifest: убедитесь в успешном collectstatic в журнале старта, обойдите главную, команду/человека, день/календарь, проект, статистику, неделю, поиск/PNG; проверьте статику и консоль в demo/real.

После проверки снимите стек теми же -p/-f и down. Добавлять -v можно только если все удаляемые тома созданы вами для этой проверки; прежние и рабочие тома сохраняются. Удалите свой временный override и образ после остановки контейнеров. Рабочий nash-den остаётся в real.

## 14. Если что-то не так

| Признак | Что проверить |
|---|---|
| `ssh nashden` не входит | `ssh -v nashden`: какой ключ предлагается; совпадает ли `HostName`; есть ли ключ в `/home/deploy/.ssh/authorized_keys`. Вход уже закрыт — раздел 2.6 |
| `sudo: unable to resolve host …` | имени сервера нет в `/etc/hosts` — раздел 2.1. Команды при этом выполняются, но с задержкой |
| `rsync: command not found` | старый вариант инструкции: ключ пользователю `deploy` не скопировался. Раздел 2.3 без `rsync`, затем проверка 2.4 |
| `git clone` / `git pull`: `Permission denied (publickey)` | ключ развёртывания добавлен в этот репозиторий; в адресе псевдоним `github-nashden`, а не `github.com` (`git remote -v`). Исправить уже клонированный: `git remote set-url origin git@github-nashden:ВЛАДЕЛЕЦ/nash-den.git` |
| `web` не становится healthy | `docker compose logs --tail 100 web`: пароль базы, `DJANGO_SECRET_KEY`, ошибка миграции |
| Сайт не открывается снаружи, в `docker compose ps` нет `caddy`, у базы `127.0.0.1:5432` | поднят стек разработки: `.env` скопирован из образца без правок. Сохраните данные и остановите стек; `.env` по разделу 7, затем `docker compose up -d --build --wait`. Удаление тома допустимо лишь после проверки, что он пустой и временный |
| Сайт не открывается снаружи | `docker compose ps` — caddy healthy и `0.0.0.0:80->80`; `sudo ufw status` — 80 открыт; у хостинга нет своего брандмауэра, закрывающего 80 |
| Bad Request (400) | адрес в браузере есть в `DJANGO_ALLOWED_HOSTS` |
| Код не принимается, страница входа возвращается | `DJANGO_SECURE_COOKIES=0` в режиме HTTP; `DJANGO_CSRF_TRUSTED_ORIGINS` совпадает с адресом в браузере |
| Код не приходит в Telegram | человек нажал «Начать»; его имя пользователя Telegram есть в карточке; контейнер `bot` healthy (`docker compose logs --tail 100 bot`) |
| После смены пароля базы сайт не подключается | пароль из `.env` применяется только при создании тома: верните прежний или смените его в самой базе |
| Кончается место | `df -h`, `docker system df`; `docker image prune -f` |
