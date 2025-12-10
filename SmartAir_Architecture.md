# SmartAir Platform - Архитектура системы

## Обзор

Платформа для мониторинга качества воздуха с поддержкой множества устройств и пользователей.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              УСТРОЙСТВА                                          │
│                                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │CO2 #001  │  │CO2 #002  │  │CO2 #003  │  │Temp #001 │  │Dust #001 │          │
│  │Спальня   │  │Гостиная  │  │Офис      │  │Балкон    │  │Кухня     │          │
│  │User: Иван│  │User: Иван│  │User: Петр│  │User: Иван│  │User: Петр│          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘          │
│       │             │             │             │             │                  │
│       └─────────────┴─────────────┴─────────────┴─────────────┘                  │
│                                   │                                              │
│                                   │ MQTT (TLS)                                   │
│                                   ▼                                              │
└───────────────────────────────────┼──────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼──────────────────────────────────────────────┐
│                                СЕРВЕР                                            │
│                                   │                                              │
│  ┌────────────────────────────────▼────────────────────────────────────────┐    │
│  │                         MQTT Broker (EMQX)                               │    │
│  │                         порт 8883 (TLS)                                  │    │
│  └────────────────────────────────┬────────────────────────────────────────┘    │
│                                   │                                              │
│  ┌────────────────────────────────▼────────────────────────────────────────┐    │
│  │                      Message Processor (Python)                          │    │
│  │  • Получает данные от устройств                                         │    │
│  │  • Сохраняет в PostgreSQL                                               │    │
│  │  • Проверяет алерты                                                     │    │
│  │  • Публикует конфиги устройствам                                        │    │
│  └──────┬─────────────────────────┬─────────────────────────────┬──────────┘    │
│         │                         │                             │                │
│         ▼                         ▼                             ▼                │
│  ┌─────────────┐          ┌─────────────┐              ┌─────────────┐          │
│  │ PostgreSQL  │          │    Redis    │              │   Telegram  │          │
│  │ (данные,    │          │ (кеш,       │              │     Bot     │          │
│  │  пользов.)  │          │  pub/sub)   │              │  (aiogram)  │          │
│  └─────────────┘          └─────────────┘              └─────────────┘          │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## ER-диаграмма базы данных

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│  ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐   │
│  │     users       │         │  user_devices   │         │    devices      │   │
│  ├─────────────────┤         ├─────────────────┤         ├─────────────────┤   │
│  │ id (PK)         │────┐    │ id (PK)         │    ┌────│ id (PK)         │   │
│  │ telegram_id     │    │    │ user_id (FK)    │◄───┘    │ device_uid      │   │
│  │ username        │    └───►│ device_id (FK)  │◄────────│ device_type     │   │
│  │ first_name      │         │ role            │         │ name            │   │
│  │ is_active       │         │ notifications   │         │ location        │   │
│  │ created_at      │         │ created_at      │         │ firmware_ver    │   │
│  └─────────────────┘         └─────────────────┘         │ last_ip         │   │
│                                                          │ last_seen       │   │
│         role:                                            │ is_online       │   │
│         • owner (владелец)                               │ created_at      │   │
│         • viewer (только смотрит)                        └────────┬────────┘   │
│         • admin (может менять настройки)                          │            │
│                                                                   │            │
│                                                                   │            │
│  ┌─────────────────┐         ┌─────────────────┐                  │            │
│  │ device_configs  │         │   telemetry     │                  │            │
│  ├─────────────────┤         ├─────────────────┤                  │            │
│  │ id (PK)         │         │ id (PK)         │                  │            │
│  │ device_id (FK)  │◄────────│ device_id (FK)  │◄─────────────────┘            │
│  │ report_interval │         │ timestamp       │                               │
│  │ alerts_enabled  │         │ co2             │                               │
│  │ co2_threshold   │         │ temperature     │                               │
│  │ night_mode_start│         │ humidity        │                               │
│  │ night_mode_end  │         │ pm25 (nullable) │                               │
│  │ updated_at      │         │ voc (nullable)  │                               │
│  └─────────────────┘         └─────────────────┘                               │
│                                                                                 │
│                                                                                 │
│  ┌─────────────────┐         ┌─────────────────┐                               │
│  │     alerts      │         │  device_types   │                               │
│  ├─────────────────┤         ├─────────────────┤                               │
│  │ id (PK)         │         │ id (PK)         │                               │
│  │ device_id (FK)  │         │ code            │  (co2, temp, dust, multi)     │
│  │ user_id (FK)    │         │ name            │                               │
│  │ type            │         │ sensors         │  (JSON: ["co2","temp","hum"]) │
│  │ message         │         │ default_config  │  (JSON)                       │
│  │ value           │         └─────────────────┘                               │
│  │ is_read         │                                                           │
│  │ created_at      │                                                           │
│  └─────────────────┘                                                           │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Связи между сущностями

```
users ◄──────── 1:N ────────► user_devices ◄──────── N:1 ────────► devices
                                   │
                                   │ role: owner | admin | viewer
                                   │ notifications: true | false
                                   │
                                   ▼
                    Один пользователь может иметь много устройств
                    Одно устройство может иметь много пользователей

devices ◄──────── 1:1 ────────► device_configs
                                   │
                                   ▼
                    Каждое устройство имеет свою конфигурацию

devices ◄──────── 1:N ────────► telemetry
                                   │
                                   ▼
                    Каждое устройство генерирует много записей телеметрии

devices ◄──────── N:1 ────────► device_types
                                   │
                                   ▼
                    Много устройств одного типа (CO2, Temp, Multi)
```

---

## Этапы разработки

### Этап 1: MVP для одного админа (ГОТОВО)
**Цель**: Работающий прототип с MQTT

```
Устройство (Pi) ──► MQTT Broker ──► Python Consumer ──► Telegram Bot
                                          │
                                          ▼
                                    PostgreSQL (минимум таблиц)
```

**Задачи:**
- [x] Поднять MQTT брокер (Mosquitto) — docker-compose.yml
- [x] Написать код устройства с MQTT клиентом — device/mqtt_client.py
- [x] Написать Python consumer для получения данных — app/mqtt/main.py
- [x] Базовый Telegram бот на сервере (aiogram) — app/bot/main.py
- [x] Минимальная БД: devices, telemetry — app/models/
- [x] Настроить Infisical для секретов
- [x] Создать alembic миграции
- [x] GitHub Actions для деплоя

**Инфраструктура (v1.2):**
```
/opt/apps/co2/
├── docker-compose.yml      # 4 сервиса: db, mqtt, processor, bot
├── Dockerfile
├── start.sh                # Запуск с Infisical
├── alembic/                # Миграции БД
├── app/
│   ├── core/               # config.py, database.py
│   ├── models/             # device.py, telemetry.py
│   ├── mqtt/               # MQTT процессор
│   └── bot/                # Telegram бот (aiogram 3.x)
├── mosquitto/config/
└── device/                 # Код для Raspberry Pi / ESP32
```

**Следующий шаг**: Задеплоить на сервер и протестировать

---

### Этап 2: Конфигурация устройств через MQTT (СЛЕДУЮЩИЙ)
**Цель**: Управление устройством через Telegram

**Задачи:**
- [ ] Задеплоить v1.2 на сервер (31.59.170.64)
- [ ] Протестировать MQTT подключение с устройства
- [ ] Добавить таблицу device_configs
- [ ] Устройство подписывается на топик конфигов
- [ ] Бот отправляет конфиги через MQTT (retained)
- [ ] Команды: /live, /watch, /stop, настройка порогов
- [ ] Упростить код устройства для ESP32

**Новая таблица:**
```sql
CREATE TABLE device_configs (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) UNIQUE,
    report_interval INTEGER DEFAULT 30,
    alerts_enabled BOOLEAN DEFAULT TRUE,
    co2_threshold INTEGER DEFAULT 1000,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Результат**: Нажал кнопку в Telegram → устройство мгновенно изменило поведение

---

### Этап 3: Многопользовательность
**Цель**: Несколько пользователей, несколько устройств

**Задачи:**
- [ ] Добавить таблицы users, user_devices
- [ ] Регистрация пользователя через /start
- [ ] Привязка устройства к пользователю (по коду)
- [ ] Роли: owner, admin, viewer
- [ ] Уведомления для всех подписанных пользователей

**Новые таблицы:**
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(100),
    first_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    device_id INTEGER REFERENCES devices(id),
    role VARCHAR(20) DEFAULT 'viewer',  -- owner, admin, viewer
    notifications BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, device_id)
);
```

**Результат**: Иван владеет 3 устройствами, жена Ивана получает уведомления

---

### Этап 4: Алерты и история
**Цель**: Умные уведомления и графики

**Задачи:**
- [ ] Таблица alerts для истории уведомлений
- [ ] Логика алертов: пороги, гистерезис, ночной режим
- [ ] API для получения истории (для графиков)
- [ ] Утренний дайджест

**Новая таблица:**
```sql
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id),
    user_id INTEGER REFERENCES users(id),
    type VARCHAR(50),          -- 'co2_high', 'co2_normal', 'device_offline'
    message TEXT,
    value REAL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Результат**: Пользователь видит историю алертов, графики CO2 за неделю

---

### Этап 5: OTA обновления
**Цель**: Безопасное обновление прошивки

**Задачи:**
- [ ] Хранение прошивок на сервере
- [ ] MQTT топик для OTA
- [ ] A/B партиции на устройстве
- [ ] Автоматический rollback при неудаче
- [ ] Версионирование прошивок в БД

**Новая таблица:**
```sql
CREATE TABLE firmware (
    id SERIAL PRIMARY KEY,
    device_type VARCHAR(50),   -- 'co2_monitor', 'temp_sensor'
    version VARCHAR(20),
    url TEXT,
    checksum VARCHAR(64),
    changelog TEXT,
    is_stable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Результат**: Нажал "Обновить" в Telegram → устройство безопасно обновилось

---

### Этап 6: Масштабирование (Kafka)
**Цель**: Поддержка 1000+ устройств

**Задачи:**
- [ ] Добавить Kafka между MQTT и обработчиком
- [ ] Разделить consumer на микросервисы
- [ ] InfluxDB для метрик (вместо PostgreSQL для telemetry)
- [ ] Grafana для мониторинга

**Результат**: Система готова к массовому рынку

---

## MQTT Топики

```
devices/{device_uid}/telemetry     # Устройство → Сервер (данные)
devices/{device_uid}/config        # Сервер → Устройство (конфиг, retained)
devices/{device_uid}/commands      # Сервер → Устройство (команды)
devices/{device_uid}/ota           # Сервер → Устройство (обновления)
devices/{device_uid}/status        # Устройство → Сервер (online/offline, LWT)
```

**Пример сообщений:**

```json
// telemetry (устройство → сервер)
{
    "device_uid": "co2_001",
    "timestamp": 1733612400,
    "co2": 920,
    "temperature": 25.1,
    "humidity": 29,
    "firmware_version": "2.0.1",
    "ip": "192.168.1.50",
    "uptime": 3600
}

// config (сервер → устройство, retained)
{
    "report_interval": 30,
    "alerts_enabled": true,
    "co2_threshold": 1000,
    "night_mode": {"start": 22, "end": 7}
}

// commands (сервер → устройство)
{
    "command": "restart",
    "timestamp": 1733612400
}

// ota (сервер → устройство)
{
    "version": "2.0.2",
    "url": "https://server.com/firmware/co2_monitor_2.0.2.bin",
    "checksum": "sha256:abc123..."
}
```

---

## Telegram бот - команды

### Для пользователя:
| Команда | Описание |
|---------|----------|
| /start | Регистрация/вход |
| /devices | Список моих устройств |
| /add | Добавить устройство (по коду) |
| /status | Текущие показания всех устройств |
| /select | Выбрать устройство для управления |
| /live | Включить live-режим |
| /stop | Остановить обновления |
| /settings | Настройки устройства |
| /share | Поделиться устройством |
| /history | История показаний |

### Для админа:
| Команда | Описание |
|---------|----------|
| /admin | Админ-панель |
| /users | Список пользователей |
| /all_devices | Все устройства в системе |
| /broadcast | Отправить сообщение всем |
| /firmware | Управление прошивками |

---

## Управление секретами (Infisical)

Все секреты и конфигурационные данные хранятся в **Infisical Cloud EU** (eu.infisical.com).

### Принцип

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ХРАНЕНИЕ СЕКРЕТОВ                                      │
│                                                                                  │
│   ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐ │
│   │   Локальная     │          │    Infisical    │          │     Сервер      │ │
│   │   разработка    │          │      Cloud      │          │   (продакшн)    │ │
│   ├─────────────────┤          ├─────────────────┤          ├─────────────────┤ │
│   │ .env файл       │          │ • BOT_TOKEN     │          │ infisical run   │ │
│   │ (не в git!)     │◄────────►│ • DATABASE_URL  │◄────────►│ загружает из    │ │
│   │                 │          │ • POSTGRES_*    │          │ cloud в env     │ │
│   │                 │          │ • ADMIN_IDS     │          │                 │ │
│   └─────────────────┘          └─────────────────┘          └─────────────────┘ │
│                                                                                  │
│   НЕ КОММИТИМ:                 ХРАНИМ ЗДЕСЬ:                ЗАПУСКАЕМ ТАК:      │
│   .env, .env.*                 все секреты                  ./start.sh          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Секреты в Infisical

| Секрет | Описание |
|--------|----------|
| `POSTGRES_USER` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `POSTGRES_DB` | Имя базы данных |
| `DATABASE_URL` | Полный URL подключения к БД |
| `DB_EXTERNAL_PORT` | Внешний порт PostgreSQL (10532) |
| `BOT_TOKEN` | Токен Telegram бота |
| `ADMIN_USER_IDS` | ID администраторов (через запятую) |
| `MQTT_PORT` | Внешний порт MQTT (10883) |
| `TZ` | Часовой пояс |

### Аутентификация

Используется **Machine Identity** (Universal Auth):
- `CLIENT_ID` — идентификатор машины
- `CLIENT_SECRET` — секрет (хранится только на сервере в start.sh)

```bash
# Аутентификация
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
  --client-id=<CLIENT_ID> \
  --client-secret=<CLIENT_SECRET> \
  --domain=https://eu.infisical.com \
  --silent --plain)

# Запуск с секретами
infisical run --projectId=<PROJECT_ID> --env=prod \
  --domain=https://eu.infisical.com \
  -- docker compose up -d
```

### Безопасность

1. **Секреты НЕ хранятся** в репозитории
2. `.env` файлы в `.gitignore`
3. Machine Identity credentials только на сервере
4. Аудит всех изменений в веб-интерфейсе Infisical
5. Шифрование at rest

---

## Развёртывание

### Структура на сервере

```
/opt/apps/co2/
├── docker-compose.yml
├── Dockerfile
├── start.sh              # Скрипт запуска с Infisical
├── alembic/              # Миграции БД
├── app/
│   ├── core/             # config.py, database.py
│   ├── models/           # SQLAlchemy модели
│   ├── mqtt/             # MQTT процессор
│   └── bot/              # Telegram бот
├── mosquitto/            # Конфиг MQTT брокера
└── device/               # Код для Raspberry Pi
```

### Порты (изолированы от других проектов)

| Сервис | Внутренний порт | Внешний порт |
|--------|-----------------|--------------|
| PostgreSQL | 5432 | 10532 |
| MQTT Broker | 1883 | 10883 |
| API (будущее) | 8000 | 10900 |

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
- uses: appleboy/ssh-action@master
  with:
    script: |
      cd /opt/apps/co2
      git pull origin main
      infisical run --projectId=${{ secrets.INFISICAL_PROJECT_ID }} --env=prod \
        -- docker compose up -d --build
```

GitHub Secrets:
- `SSH_HOST`, `SSH_USER`, `SSH_KEY` — для доступа к серверу
- `INFISICAL_PROJECT_ID` — ID проекта в Infisical

---

## Следующий шаг

**Этап 1 завершён!** Код v1.2 готов.

### Ближайшие действия:
1. **Создать GitHub репозиторий** для CO2 Monitor
2. **Задеплоить на сервер** (31.59.170.64:/opt/apps/co2)
3. **Запустить и протестировать**:
   - MQTT брокер принимает подключения на порту 10883
   - Бот отвечает на /start и /status
   - Процессор сохраняет телеметрию в БД
4. **Подключить устройство** (Raspberry Pi) и отправить первые данные
5. **Перейти к Этапу 2**: управление устройством через Telegram
