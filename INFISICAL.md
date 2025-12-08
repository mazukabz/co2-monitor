# Infisical — Документация для CO2 Monitor

## 1. Что такое Infisical

**Infisical** — open-source менеджер секретов. Мы используем **Infisical Cloud EU** (eu.infisical.com) для хранения всех секретов проекта.

**Преимущества:**
- Секреты не хранятся в `.env` файлах в репозитории
- Централизованное управление (веб-интерфейс)
- Аудит изменений
- Machine Identity для серверов

---

## 2. Данные проекта CO2 Monitor

| Параметр | Значение |
|----------|----------|
| **URL консоли** | https://eu.infisical.com |
| **Project ID** | `04ac3c18-2975-4e2a-9a08-f5b831f13d9e` |
| **Environment** | `prod` |
| **Machine Identity Client ID** | `97bc8628-39ac-47ed-adc4-9db614fe717a` |
| **Machine Identity Client Secret** | `a15ca6c4e4d9b9e6b248cff1a5bc1680053c2bd281194c49ef77cb292387bd07` |

### Сервер
| Параметр | Значение |
|----------|----------|
| **IP** | 31.59.170.64 |
| **Путь проекта** | /opt/apps/co2 |

---

## 3. Структура секретов в Infisical

Секреты разделены на две папки:

### /co2_secrets (чувствительные данные)
```
┌───────────────────┬─────────────────────────────────────────────────┐
│ SECRET NAME       │ ОПИСАНИЕ                                        │
├───────────────────┼─────────────────────────────────────────────────┤
│ POSTGRES_PASSWORD │ Пароль PostgreSQL                               │
│ BOT_TOKEN         │ Токен Telegram бота от @BotFather               │
│ SSH_PRIVATE_KEY   │ Приватный SSH ключ для деплоя                   │
└───────────────────┴─────────────────────────────────────────────────┘
```

### /co2_configs (конфигурация)
```
┌────────────────────┬─────────────────────────────────────────────────┐
│ SECRET NAME        │ ОПИСАНИЕ                                        │
├────────────────────┼─────────────────────────────────────────────────┤
│ POSTGRES_USER      │ co2_user                                        │
│ POSTGRES_DB        │ co2_db                                          │
│ DATABASE_URL       │ postgresql+asyncpg://...@co2_db:5432/co2_db     │
│ DB_EXTERNAL_PORT   │ 10532 (внешний доступ к PostgreSQL)             │
│ MQTT_PORT          │ 10883 (внешний доступ для устройств)            │
│ MQTT_EXTERNAL_PORT │ 10883 (для API — порт в прошивке устройств)     │
│ API_PORT           │ 10900 (API для OTA обновлений)                  │
│ ADMIN_USER_IDS     │ 5562787884                                      │
│ TZ                 │ Europe/Moscow                                   │
│ SSH_HOST           │ 31.59.170.64 (IP сервера для деплоя)            │
│ SSH_USER           │ root (SSH пользователь для деплоя)              │
└────────────────────┴─────────────────────────────────────────────────┘
```

### Важно про порты!
- **Внешние порты** (10532, 10883, 10900) — берутся из Infisical
- **Внутренние порты** (5432, 1883, 8000) — захардкожены в Docker, не трогать
- **НЕ МЕНЯТЬ порты** без согласования!

**Важно:** Флаг `--recursive` в `infisical run` загружает секреты из всех подпапок.

---

## 4. Установка Infisical CLI на сервер

```bash
# Добавить репозиторий
curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | sudo bash

# Установить CLI
sudo apt-get update && sudo apt-get install -y infisical

# Проверить версию
infisical --version
```

---

## 5. start.sh для запуска с секретами

Файл `/opt/apps/co2/start.sh`:

```bash
#!/bin/bash
# CO2 Monitor Startup Script with Infisical Secrets

set -e
cd /opt/apps/co2

echo "🔐 Authenticating with Infisical..."
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
  --client-id=97bc8628-39ac-47ed-adc4-9db614fe717a \
  --client-secret=a15ca6c4e4d9b9e6b248cff1a5bc1680053c2bd281194c49ef77cb292387bd07 \
  --domain=https://eu.infisical.com \
  --silent --plain)

if [ -z "$INFISICAL_TOKEN" ]; then
  echo "❌ Failed to authenticate with Infisical"
  exit 1
fi

echo "✅ Authenticated successfully"
echo "🚀 Starting services with secrets from Infisical..."

infisical run \
  --projectId=04ac3c18-2975-4e2a-9a08-f5b831f13d9e \
  --env=prod \
  --recursive \
  --domain=https://eu.infisical.com \
  -- docker compose up -d --build

echo "✅ Services started!"
docker compose ps
```

**Как это работает:**
1. `infisical login` — получает токен доступа через Machine Identity
2. `infisical run` — загружает все секреты как переменные окружения
3. `docker compose up` — запускается с этими переменными

---

## 6. CLI команды для работы

### Аутентификация
```bash
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
  --client-id=97bc8628-39ac-47ed-adc4-9db614fe717a \
  --client-secret=a15ca6c4e4d9b9e6b248cff1a5bc1680053c2bd281194c49ef77cb292387bd07 \
  --domain=https://eu.infisical.com \
  --silent --plain)
```

### Просмотр секретов
```bash
# Из папки /co2_secrets
infisical secrets \
  --projectId=04ac3c18-2975-4e2a-9a08-f5b831f13d9e \
  --env=prod \
  --path=/co2_secrets \
  --domain=https://eu.infisical.com

# Из папки /co2_configs
infisical secrets \
  --projectId=04ac3c18-2975-4e2a-9a08-f5b831f13d9e \
  --env=prod \
  --path=/co2_configs \
  --domain=https://eu.infisical.com
```

### Установить секрет
```bash
# В папку секретов
infisical secrets set BOT_TOKEN="your_token" \
  --projectId=04ac3c18-2975-4e2a-9a08-f5b831f13d9e \
  --env=prod \
  --path=/co2_secrets \
  --domain=https://eu.infisical.com

# В папку конфигов
infisical secrets set MQTT_PORT="10883" \
  --projectId=04ac3c18-2975-4e2a-9a08-f5b831f13d9e \
  --env=prod \
  --path=/co2_configs \
  --domain=https://eu.infisical.com
```

### Запустить команду с секретами
```bash
# --recursive загружает из всех подпапок
infisical run \
  --projectId=04ac3c18-2975-4e2a-9a08-f5b831f13d9e \
  --env=prod \
  --recursive \
  --domain=https://eu.infisical.com \
  -- docker compose up -d
```

---

## 7. Добавление нового секрета

### Шаг 1: Добавить в Infisical
```bash
infisical secrets set NEW_VAR="value" --projectId=... --env=prod --domain=https://eu.infisical.com
```

### Шаг 2: Добавить в docker-compose.yml
```yaml
co2_bot:
  environment:
    - NEW_VAR=${NEW_VAR:-default_value}
```

### Шаг 3: Добавить в app/core/config.py
```python
class Settings(BaseSettings):
    new_var: str = "default_value"
```

### Шаг 4: Перезапустить сервисы
```bash
./start.sh
```

---

## 8. Безопасность

1. **Client Secret** хранится только на сервере в `start.sh`
2. `.env` файлы НЕ коммитятся (в .gitignore)
3. Infisical шифрует секреты at rest
4. Аудит всех изменений в веб-интерфейсе
