# Архитектура

Источник — схема технологического стека (30.10.2026) и слайд «Архитектура» в презентации требований. Стартовое окружение — Docker Compose. Причины выбора — ADR-0002 (REST + SSE), ADR-0003 (модульный монолит), ADR-0004 (ClickHouse), ADR-0005 (Caddy), ADR-0007 (контракты и инфраструктура), ADR-0009 (Signals); что именно хранить в ClickHouse — ещё обсуждается (ADR-0001).

```
Браузер: Angular SPA (Taiga UI)
   │ HTTPS: REST + SSE + статика
Caddy — автоматический HTTPS, раздача SPA, reverse proxy /api, проксирование SSE
   │ /api
Java: один процесс Spring Boot + Spring Modulith          ── SQL (Spring Data JDBC, Flyway) ──> PostgreSQL
   │ gRPC: задание и команды ↔ события и результат
C++: Simulation Worker (gRPC server) → Simulation Core      ── read-only ──> ClickHouse
                                                                               ↑
Подготовка данных вне приложения: Python-импорт из MOEX / MFD / внешних архивов
```

## Репозитории

| Репозиторий | Что внутри | Стек |
|---|---|---|
| `frontend` | Angular SPA | последняя версия Angular, standalone-компоненты, Signals для состояния (ADR-0009), Taiga UI 4; образ — `caddy` с собранной SPA в `/srv` |
| `backend` | HTTP API, модули ниже; `deploy/` — Docker Compose и `Caddyfile` | Java 25, Spring Boot 4.1.2 + Spring Modulith 2.1.2, Gradle 9.8.2 (Kotlin DSL), пакет `ru.ttsc.lab` |
| `core` | Simulation Core (библиотека) и Simulation Worker (gRPC-сервер) | C++20, CMake, vcpkg, GoogleTest, gRPC; локальная сборка в Docker, CI на ubuntu-24.04 |
| `documentation` | требования, инварианты, архитектура, ADR, статус, DSL; wiki — Vision и Глоссарий | — |

Стек — решение владельца продукта (02.11.2026).

## Контракты (ADR-0007)

| Контракт | Источник правды | Копии | Генерация |
|---|---|---|---|
| gRPC Java ↔ C++ | `core/proto/` | `backend/src/main/proto/` — скрипт синхронизации, CI сверяет с `core` | C++ — CMake в `core`; Java — Gradle в `backend` |
| REST и SSE Angular ↔ Java | `backend/api/openapi.yaml`, contract-first; события SSE — схемы в `components/schemas` | во `frontend` — скрипт синхронизации, CI сверяет с `backend` | TS-клиент — при сборке `frontend` |

Деньги в контрактах: в `.proto` — `Decimal { units, nano }`, в REST — строка (ADR-0008, предложен).

## Java-модули (Spring Modulith)

- **api** — сквозная часть HTTP API: Spring Security, обработка ошибок, служебные эндпоинты (`/api/health`). Spring MVC, REST, SSE, Validation. Контроллеры бизнес-функций живут не здесь, а в пакете `<модуль>.web` своего модуля (`ru.ttsc.lab.sessions.web` и т. п.).
- **identity** — пользователи, роли, права.
- **sessions** — сессии и команды пользователя: запуск, пауза, шаг, заявка; фиксирует версию стратегии.
- **workshop** — стратегии и неизменяемые версии, DSL, параметры, публикация.
- **simulation** — оркестрация и gRPC-клиент, фоновые задания, версия данных и период, команды в C++, сохранение событий и снимков. Свечи не проходят через Java в цикле.
- **marketdata** — каталог инструментов, периодов и версий, проверка наличия истории для сессии. Доступ к ClickHouse только на чтение; данные не скачивает и тики в C++ не передаёт.
- **analysis** — сравнение и отчёты, обработка события `RunCompleted`, чтение сохранённых результатов.

Связи: `sessions → workshop` (получить версию), `sessions → simulation` (запустить или продолжить), `simulation → marketdata` (зафиксировать готовую версию данных), `simulation → analysis` (`RunCompleted`).

Границы модулей:
- вызовы между модулями — через публичные Java-интерфейсы, уведомления — через внутренние события Spring Modulith;
- одна PostgreSQL, у каждого модуля своя схема (`identity`, `sessions`, `workshop`, `simulation`, `marketdata`, `analysis`; создаются в `backend` миграцией `V1__baseline.sql`); модуль создаёт таблицы только в своей схеме, чужие схемы, entity и репозитории напрямую не использует;
- границы проверяются в CI: `ApplicationModules.verify()`.

## C++

- **Simulation Core** — независимая библиотека: рыночный цикл выполняется локально; время, индикаторы, исполнение DSL, заявки, риск-проверки, портфель. CLI для replay и тестов.
- Деньги, портфель, издержки и метрики отчёта считает только `core`; Java их хранит и отдаёт (ADR-0008, предложен).
- Разбор DSL, линтер и проверка на чтение будущего — одна реализация в `core`; `workshop` получает диагностики от Simulation Worker (`dsl.md`, предложено). Разбор расхождений (ФТ-19, ФТ-20) тоже считает `core`: стратегия исполняется в состоянии портфеля человека.
- **Simulation Worker** — gRPC-сервер (Protocol Buffers) и адаптер чтения ClickHouse. Получает от Java задание (версия, период, параметры), отдаёт события и результат. К MOEX и PostgreSQL не обращается.

## Хранилища

- **PostgreSQL 17** — пользователи, стратегии, сессии, команды, сделки, результаты, очередь фоновых заданий. Доступ только из Java.
- **ClickHouse 25.8** — история сделок и свечей (MergeTree), постоянный Docker volume. Python пишет пакетным импортом после проверки; Java читает каталог и покрытие; C++ читает диапазоны крупными блоками.
- К внешним источникам истории обращается только скрипт подготовки данных; приложение работает с локальным ClickHouse.

Возможное расширение: RabbitMQ для отдельных batch-воркеров (в стартовый стек не входит).
