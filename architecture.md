# Архитектура

Источник — схема технологического стека (30.10.2026) и слайд «Архитектура» в презентации требований. Стартовое окружение — Docker Compose. Причины выбора — ADR-0002 (REST + SSE), ADR-0003 (модульный монолит), ADR-0004 (ClickHouse), ADR-0005 (Caddy), ADR-0007 (контракты и инфраструктура), ADR-0009 (Signals), ADR-0010–0012 (библиотеки фронтенда), ADR-0013 (чтение ClickHouse из C++); что именно хранить в ClickHouse — ещё обсуждается (ADR-0001).

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

- **api** — сквозная часть HTTP API: Spring Security, обработка ошибок, служебные эндпоинты (`/api/health`). Контроллеры бизнес-функций живут в пакете `<модуль>.web` своего модуля; исключения модуля переводятся в `Problem` (`application/problem+json`) его `@RestControllerAdvice`.
- **config** — настройки `lab.*` (`LabProperties`); ни от кого не зависит.
- **identity** — пользователи, роли (`USER`, `MODERATOR`), вход по cookie-сессии с CSRF; публично — `CurrentUser`, `UserDirectory` (имена пользователей для других модулей). Id пользователя — `bigint`.
- **worker** — клиент gRPC к Simulation Worker: `WorkerClient`, перевод денег `Decimal{units, nano}` ↔ `BigDecimal` (`Decimals`), сборка `MarketSpec` (`MarketSpecs`), дайджест прогона (`Digests`). Отдельный модуль, чтобы `workshop`, `sessions` и `simulation` звали воркер без циклов.
- **marketdata** — каталог снапшотов, бумаг, торговых дней, выбор периода сессии. ClickHouse — только `SELECT` через собственный пул; данные не скачивает, бары в C++ не передаёт. Индексы (IMOEX) в каталог бумаг не попадают.
- **workshop** — стратегии, черновики, неизменяемые версии (INV-5), публикация, форки, скрытие, запросы на удаление и модерация; проверка DSL — через воркер.
- **sessions** — ручные сессии: создание, журнал «номер свечи + заявка» (INV-8), слепая маска (INV-7), часы плеера и SSE, заявки, завершение и раскрытие, данные для воспроизведения.
- **simulation** — очередь фоновых заданий (`JobQueue`, `JobHandler`), прогоны алгоритмов (`RunService`), стресс-пары, walk-forward, повтор прогона со сверкой дайджеста (UC-18).
- **analysis** — отчёты и история, разбор расхождений, рейтинг и каталог; слушает события других модулей.

Зависимости модулей (без циклов, проверяет `ApplicationModules.verify()` в CI): `config`, `identity` — ни от кого; `worker` → `config`; `marketdata` → `config`; `workshop` → `worker`, `identity`, `config`; `sessions` → `worker`, `marketdata`, `identity`, `config`; `simulation` → `worker`, `workshop`, `marketdata`, `identity`, `config`; `analysis` → все остальные.

События Spring Modulith (объявлены в модуле-источнике, слушает `analysis`, кроме первого):
- `SessionEndReached` (`sessions`) — часы дошли до конца периода или банкротства; публикуется в транзакции, записавшей статус; слушает `sessions` (завершение).
- `SessionFinished` (`sessions`) — один раз на сессию, в транзакции завершения (досрочно — `FinishService`, конец периода и банкротство — по `SessionEndReached`); несёт `Report` и `MarketSpec` в байтах. Слушатель — после коммита (`@ApplicationModuleListener`).
- `RunCompleted` (`simulation`) — прогон досчитан (в том числе отрезки walk-forward и окна рейтинга); несёт `RunResult` и `MarketSpec`. Отчёты по прогонам с `purpose = RATING` не сохраняются: в них даты закрытых окон.
- `VersionPublished` (`workshop`) — версия опубликована; запускает расчёт её рейтинга.

Очередь фоновых заданий — таблица `simulation.jobs` в PostgreSQL: захват `FOR UPDATE SKIP LOCKED` с арендой (`lab.jobs.lease`, продление каждые `lease / 2`), `lab.jobs.concurrency` потоков, повтор после сбоя с задержкой 5 с × номер попытки до `lab.jobs.max-attempts`, задание с истёкшей арендой после перезапуска возвращается в очередь. Типы заданий: `RUN`, `WALK_FORWARD`, `COMPARISON`, `RATING`.

Границы модулей:
- вызовы между модулями — через публичные Java-интерфейсы, уведомления — через события Spring Modulith;
- одна PostgreSQL, у каждого модуля своя схема (`identity`, `sessions`, `workshop`, `simulation`, `marketdata`, `analysis`; создаются в `backend` миграцией `V1__baseline.sql`, номера миграций модулей V2…V12 закреплены планом); модуль создаёт таблицы только в своей схеме, чужие схемы, entity и репозитории напрямую не использует;
- полей `double`/`float` в `ru.ttsc.lab` нет, кроме пакета метрик `analysis.metrics` (`MoneyTypesArchTest`, INV-6).

## C++

- **Simulation Core** — независимая библиотека без gRPC: деньги (`Decimal`), рыночные данные и шкала времени сессии, исполнение заявок, портфель, движок сессии (проигрывание журнала), DSL (разбор, проверки, линтер, интерпретатор), прогон стратегии с проверками во время исполнения, метрики отчёта, стресс, цепочка «наивный → честный», walk-forward, разбор расхождений.
- Деньги, портфель, издержки и метрики отчёта считает только `core`; Java их хранит и отдаёт (ADR-0008, предложен).
- **Simulation Worker** — gRPC-сервер (`core/proto/simulation.proto`, пакет `pac.simulation.v1`). Состояния сессий не хранит: каждый вызов `ReplaySession` заново читает бары и проигрывает журнал до курсора (INV-8). К MOEX и PostgreSQL не обращается.

| RPC | Что делает |
|---|---|
| `Ping` | версия ядра |
| `CheckStrategy` | разбор DSL, проверки и линтер → диагностики и параметры |
| `ReplaySession` | журнал сессии до курсора → события шагов, история баров, портфель, заявки, результаты команд, отчёт |
| `GetBars` | бары шагов из диапазона (воспроизведение) |
| `RunBacktest` | прогон стратегии (поток прогресса), стресс, отчёт, цепочка издержек ФТ-24 |
| `RunWalkForward` | walk-forward (поток прогресса) |
| `AnalyzeDivergences` | разбор расхождений человек ↔ алгоритмы, консенсус, независимые портфели |

Ошибки RPC: нет данных снапшота, бумаги или баров — `FAILED_PRECONDITION`; прочие ошибки данных — `NOT_FOUND`; ошибка DSL или параметров — `INVALID_ARGUMENT`; ClickHouse недоступен — `UNAVAILABLE`; испорченные данные и нарушение целостности движка — `INTERNAL`.

ClickHouse воркер читает по HTTP-интерфейсу через libcurl (ADR-0013): `readonly=1`, только `snapshots_ready`, свечи — из `candles` или `candles_from_trades`, календарь — `trading_calendar`.

## Окружение (Docker Compose)

`backend/deploy/docker-compose.yml`: `caddy` (образ frontend из `../../frontend`, раздаёт SPA и проксирует `/api`), `backend`, `worker` (из `../../core`), `postgres`, `clickhouse`. Порты наружу публикует только `caddy` (INV-10, проверка `deploy/tests/compose-ports.test.sh`). Для рейтинга обязательна переменная `RATING_SEED`.

## Хранилища

- **PostgreSQL 17** — пользователи, стратегии, сессии, команды, сделки, результаты, очередь фоновых заданий. Доступ только из Java.
- **ClickHouse 25.8** — история сделок и свечей (MergeTree), постоянный Docker volume. Python пишет пакетным импортом после проверки; Java читает каталог и покрытие; C++ читает диапазоны крупными блоками.
- К внешним источникам истории обращается только скрипт подготовки данных; приложение работает с локальным ClickHouse.

Возможное расширение: RabbitMQ для отдельных batch-воркеров (в стартовый стек не входит).
