# План реализации ФТ-1…24 и НФТ-1…6

> **Для агентов-исполнителей:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans; задачи выполняются по одной, шаги отмечаются `- [ ]`. Каждая задача — отдельный issue и отдельный PR в своём репозитории (`workflow.md`).

**Цель:** продукт целиком — арена ручной торговли со слепым режимом, мастерская стратегий на DSL с честной проверкой, отчёты, разбор расхождений человек ↔ алгоритм, рейтинг, walk-forward, стресс и наивный/честный прогон.

**Архитектура:** C++ `core` считает всё, что касается рынка, денег и стратегий (исполнение, портфель, DSL, метрики, расхождения); `simulation_worker` отдаёт это по gRPC и сам состояния сессий не хранит — состояние всегда получается проигрыванием журнала (INV-8). Java `backend` хранит пользователей, сессии с журналом, стратегии, прогоны и отчёты, ведёт часы плеера и очередь заданий, отдаёт REST + SSE. Angular `frontend` только показывает и шлёт команды.

**Стек:** C++20, CMake, GoogleTest, gRPC/protobuf, libcurl (HTTP-интерфейс ClickHouse); Java 25, Spring Boot 4.1.2, Spring Modulith 2.1.2, Gradle 9.8.2, PostgreSQL 17 + Flyway, ClickHouse 25.8; Angular 22 (standalone, Signals), Taiga UI 4, Vitest, `ng-openapi-gen`, `lightweight-charts`, CodeMirror 6.

**Спецификация:** `requirements.md`, `invariants.md`, `decisions.md`, `dsl.md`, `use-cases.md`, `architecture.md`, ADR-0007, ADR-0008, ADR-0009; схема ClickHouse — `backend/deploy/clickhouse/schema/*.sql` (задача DI). План опирается на них; противоречие плана и спецификации решается в пользу спецификации, о расхождении — комментарий в issue.

## Глобальные ограничения

- Деньги и цены: C++ — `core::Decimal` (9 знаков, `__int128`, как в `core/money`), proto — `pac.simulation.v1.Decimal{units, nano}`, Java — `BigDecimal`, REST — строка `^-?\d{1,19}(\.\d{1,9})?$`, PostgreSQL — `numeric(38,9)`. `double` для денег запрещён (INV-6); метрики — `double` (`decisions.md`, «Деньги и округление», п. 9–11).
- Правила округления — только из `decisions.md`, «Деньги и округление»; режимы называются как в `java.math.RoundingMode`.
- Значения по умолчанию модели исполнения: комиссия 0,0005; биржевой сбор 0,0001; спред s = 0,001; κ = 0,1; лимит ликвидности p = 0,10; капитал 1 000 000 ₽ (`decisions.md`).
- Количество — целые лоты (`int64` / `long`). Объём бара — в лотах.
- Идентификаторы — по-английски; комментарии, сообщения, тексты UI, коммиты — по-русски, без префиксов Conventional Commits (`workflow.md`).
- Пакет proto — `pac.simulation.v1`, `option java_package = "pac.simulation.v1"`, `option java_multiple_files = true` (решение плана, см. «Соглашения»).
- Детерминизм (INV-4): в `core` нет часов, `std::random_device`, `unordered_*` в расчёте, обхода по адресам; сборка с `-ffp-contract=off`, без `-ffast-math`.
- Сборка `core` — только `-j2`; `backend` — `-Xmx768m`, один демон Gradle (мало RAM у команды).
- Версии: Spring Boot 4.1.2, Modulith 2.1.2, Gradle 9.8.2, PostgreSQL 17, ClickHouse 25.8, Node 24, npm 11.

## На что смотреть при ревью

Пять ситуаций, которые спецификация подразумевает, но легко пропустить. Тест на каждую уже вписан в задачу-владельца.

1. Повторная отправка заявки (двойной клик, повтор запроса после обрыва) не должна создавать вторую заявку: `clientOrderId` идемпотентен — тест в задаче 32.
2. Тик часов и заявка одновременно на одной сессии (или две вкладки): курсор не прыгает, заявка привязывается к одному шагу — тест в задачах 31 и 32.
3. В многобумажной сессии у бумаги нет бара на шаге (неликвид, разрыв торгов): её заявки ждут следующего бара этой бумаги, а не исполняются по чужому бару — тест в задаче 11.
4. Объём бара меньше 1/p лота (floor(p·V) = 0): рыночная заявка снимается с `LIQUIDITY_LIMIT`, лимитная остаётся активной — тест в задаче 11.
5. Перезапуск backend во время игры или прогона: сессия открывается на паузе на том же шаге, задание прогона возвращается в очередь и доводится — тесты в задачах 31 и 35.

---

## Соглашения плана

**Пакет proto.** Остаётся `pac.simulation.v1` (уже в `core/proto/` после каркаса и задачи 5). Java-классы генерируются в пакет `pac.simulation.v1` — вне `ru.ttsc.lab`, поэтому Spring Modulith и `MoneyTypesArchTest` их не анализируют. C++ — пространство имён `pac::simulation::v1`.

**Генерация по OpenAPI.** Backend пишет DTO руками (records в `<модуль>.web`), соответствие контракту проверяет тест `OpenApiContractAssert` (задача 4) в каждом тесте контроллера. Frontend генерирует клиент `ng-openapi-gen` в `src/app/core/api/generated/` (не коммитится).

**Владение общими файлами.** Только перечисленные задачи меняют эти файлы; остальные их не трогают:

| Файл | Кто меняет |
|---|---|
| `core/proto/*.proto`, `core/proto/CMakeLists.txt` | 1 |
| `core/CMakeLists.txt`, `core/src/core/CMakeLists.txt`, `core/tests/CMakeLists.txt`, `core/src/worker/CMakeLists.txt` | 3 (после 34) |
| `core/vcpkg.json`, `core/Dockerfile*`, `core/.github/workflows/ci.yml` | 34 (уже в работе); после неё — по issue |
| `core/src/worker/worker_service.{hpp,cpp}`, `core/src/worker/handlers.hpp` | 23 |
| `backend/build.gradle.kts`, `backend/src/main/resources/application.yml`, `backend/.github/workflows/ci.yml` (до задачи 52), `backend/api/openapi.yaml` | 4 (yaml — 2) |
| `backend/src/main/java/ru/ttsc/lab/api/SecurityConfig.java` | 12, затем 4 |
| `backend/deploy/docker-compose.yml`, `backend/deploy/Caddyfile` | 52 (после DI) |
| `frontend/package.json`, `package-lock.json`, `angular.json`, `src/app/app.routes.ts`, `src/app/app.config.ts`, `.github/workflows/ci.yml` | 6 (после 13 и 63) |
| `documentation/invariants.md`, `architecture.md`, `status.md` | 54 |

Нашёл, что в общий файл нужно добавить строку, — не правь его в своей задаче: добавь в issue задачи-владельца комментарий или заведи маленький issue.

**Области `core`.** Код области `<area>`: заголовки `src/core/include/core/<area>/*.hpp`, исходники `src/core/<area>/*.cpp`, тесты `tests/<area>/*_test.cpp`, тесты воркера `tests/worker/*_test.cpp`. Задача 3 заранее создаёт `CMakeLists.txt` всех областей (`money market portfolio exec engine dsl run report analysis`) с `file(GLOB CONFIGURE_DEPENDS …)`, поэтому новый файл подхватывается сам и задачи CMake не правят. Стиль имён — как в `core/money`: методы `camelCase`, типы `PascalCase`, пространство имён `core`.

**Миграции Flyway** (номера закреплены, `spring.flyway.out-of-order=true` включает задача 4):

| Версия | Задача | Модуль |
|---|---|---|
| V2 | 12 | identity (уже в работе) |
| V3 | 30 | sessions |
| V4 | 38 | workshop: стратегии |
| V5 | 39 | workshop: версии, эталонная стратегия |
| V6 | 41 | workshop: запросы на удаление |
| V7 | 35 | simulation: задания |
| V8 | 36 | simulation: прогоны |
| V9 | 37 | simulation: walk-forward |
| V10 | 42 | analysis: отчёты |
| V11 | 43 | analysis: сравнения |
| V12 | 44 | analysis: рейтинг |

**Настройки backend** (`application.yml`, все добавляет задача 4 с этими значениями; задачи только читают):

```yaml
lab:
  worker: { host: localhost, port: 50051, unary-deadline: 10s, stream-deadline: 30m }
  clickhouse: { url: "http://localhost:8123", database: default, user: default, password: "" }
  costs: { commission-rate: "0.0005", exchange-fee-rate: "0.0001", spread: "0.001", slippage-kappa: "0.1", liquidity-share: "0.10" }
  session:
    initial-cash: "1000000"
    manual-durations: [20, 60, 120, 250]
    manual-max-bars: 5000
    max-instruments: 5
    disconnect-pause-after: 5s
  marketdata: { blind-pool: [SBER, GAZP, LKOH, GMKN, NVTK, ROSN, TATN, YDEX, PLZL, SNGS, MGNT, VTBR, T, MTSS, ALRS, CHMF, NLMK, MOEX, IRAO, PHOR] }
  jobs: { concurrency: 2, poll-interval: 1s, lease: 10m, max-attempts: 3 }
  rating: { seed: "${RATING_SEED:0}", windows: 30, window-days: 120, regime-threshold: "0.05" }
  walk-forward: { fit-days: 250, test-days: 63, shift-days: 63, max-grid: 200 }
```

`lab.marketdata.blind-pool` — список IMOEX из конфигурации (`decisions.md`, «Запуск сессии и прогона»); команда правит его при импорте.

**Шаг и курсор.** Шаг (`step`) — номер в общей шкале времени сессии: отсортированное объединение моментов начала баров всех бумаг сессии, нумерация с 0. Курсор — последний показанный шаг; при создании сессии курсор = 0 (плеер на паузе с первой свечой, UC-2). Команда из журнала с `step = k` действует с шага k+1 (INV-2). `order_id = seq · 2 + leg`, где `seq` — номер записи журнала с 0, `leg` — 0 или 1 (вторая нога OCO).

**Волны.** Номер волны = 1 + наибольшая волна зависимостей; задачи одной волны можно брать параллельно, общих файлов у них нет. Сводка — в конце плана.

---

## Трек 0. Контракты и сборка

### Задача 1: gRPC-контракт `simulation.proto`

- **Репозиторий:** core. **Размер:** S. **Волна:** 1.
- **Зависит от:** 5 (в ней появился `proto/common.proto` с `Decimal`).
- **Связано:** ADR-0007, ADR-0008, ФТ-1…24, INV-1, INV-2, INV-8.

**Files:**
- Modify: `core/proto/simulation.proto` (полный контракт ниже), `core/proto/common.proto` (только опции `java_package`, `java_multiple_files`).
- Test: новый тест в `core/tests/worker_ping_test.cpp` (файл уже в `worker_tests`; задача 3 его не двигает).

Контракт (комментарии к полям — по-русски, в файле):

```proto
syntax = "proto3";
package pac.simulation.v1;
option java_package = "pac.simulation.v1";
option java_multiple_files = true;
import "common.proto";  // Decimal

service SimulationWorker {
  rpc Ping(PingRequest) returns (PingResponse);
  rpc CheckStrategy(CheckStrategyRequest) returns (CheckStrategyResponse);
  rpc ReplaySession(ReplaySessionRequest) returns (ReplaySessionResponse);
  rpc GetBars(GetBarsRequest) returns (GetBarsResponse);
  rpc RunBacktest(RunBacktestRequest) returns (stream RunBacktestUpdate);
  rpc RunWalkForward(WalkForwardRequest) returns (stream WalkForwardUpdate);
  rpc AnalyzeDivergences(DivergenceRequest) returns (DivergenceResponse);
}
message PingRequest {}
message PingResponse { string core_version = 1; }

enum Timeframe { TIMEFRAME_UNSPECIFIED = 0; S1 = 1; S10 = 2; M1 = 3; M5 = 4; M10 = 5; M15 = 6; H1 = 7; D1 = 8; }
enum Level { LEVEL_UNSPECIFIED = 0; OK = 1; WARNING = 2; ERROR = 3; }
enum Side { SIDE_UNSPECIFIED = 0; BUY = 1; SELL = 2; }
enum OrderType { ORDER_TYPE_UNSPECIFIED = 0; MARKET = 1; LIMIT = 2; STOP = 3; STOP_LIMIT = 4; TAKE_PROFIT = 5; TRAILING_STOP = 6; }
enum TimeInForce { TIME_IN_FORCE_UNSPECIFIED = 0; DAY = 1; GTC = 2; }
enum OrderStatus { ORDER_STATUS_UNSPECIFIED = 0; ACTIVE = 1; PARTIALLY_FILLED = 2; FILLED = 3; CANCELLED = 4; EXPIRED = 5; REJECTED = 6; }
enum Reason {
  REASON_UNSPECIFIED = 0; INVALID_PARAMS = 1; INSUFFICIENT_CASH = 2; INSUFFICIENT_POSITION = 3;
  SESSION_NOT_ACTIVE = 4; ORDER_NOT_ACTIVE = 5; LIQUIDITY_LIMIT = 6; OCO_SIBLING_FILLED = 7;
  POSITION_CLOSED = 8; REPLACED = 9; SESSION_END = 10; CANCELLED_BY_USER = 11; RULE_REPLACED = 12; DAY_EXPIRED = 13;
}

// Данные и условия: снапшот, бумаги, период, шаг, издержки, капитал.
message Instrument { string key = 1; string ticker = 2; int64 lot_size = 3; Decimal price_step = 4; }
message CostConfig { Decimal commission_rate = 1; Decimal exchange_fee_rate = 2; Decimal spread = 3; Decimal slippage_kappa = 4; Decimal liquidity_share = 5; }
message MarketSpec {
  string snapshot_id = 1;               // UUID снапшота ClickHouse
  repeated Instrument instruments = 2;  // порядок = порядок обработки (dsl.md)
  Timeframe timeframe = 3;
  string from_date = 4;                 // ISO yyyy-mm-dd, включительно, московская дата
  string to_date = 5;
  CostConfig costs = 6;
  Decimal initial_cash = 7;
  string benchmark_ticker = 8;          // "IMOEX" или пусто
  bool naive = 9;                       // наивный прогон ФТ-24: нулевые издержки, исполнение по close бара решения
}
message Bar {
  int64 step = 1; string instrument_key = 2; int64 time_unix_ms = 3; int32 trading_day = 4;
  Decimal open = 5; Decimal high = 6; Decimal low = 7; Decimal close = 8;
  int64 volume_lots = 9; bool after_halt = 10;
}

// Журнал (INV-8).
message OrderSpec {
  string instrument_key = 1; Side side = 2; OrderType type = 3; int64 lots = 4;
  Decimal limit_price = 5; Decimal stop_price = 6; Decimal trailing_percent = 7; TimeInForce time_in_force = 8;
}
message PlaceOrder { OrderSpec order = 1; OrderSpec oco_with = 2; }   // oco_with пустой (lots = 0) — без OCO
message CancelOrder { int64 order_id = 1; }
message ReplaceOrder { int64 order_id = 1; PlaceOrder replacement = 2; }
message JournalEntry {
  int64 seq = 1; int64 step = 2;
  oneof command { PlaceOrder place = 3; CancelOrder cancel = 4; ReplaceOrder replace = 5; }
}

// Состояние.
message Order {
  int64 id = 1; OrderSpec spec = 2; int64 placed_step = 3; OrderStatus status = 4; Reason reason = 5;
  string invalid_field = 6; int64 filled_lots = 7; int64 oco_sibling_id = 8; string rule_name = 9;
  string because = 10; Decimal trailing_stop_level = 11; int64 closed_step = 12;
}
message Fill {
  int64 order_id = 1; int64 step = 2; string instrument_key = 3; Side side = 4; int64 lots = 5;
  Decimal price = 6; Decimal base_price = 7; Decimal value = 8; Decimal commission = 9; Decimal exchange_fee = 10;
  bool stop_and_take_same_bar = 11; Decimal spread_cost = 12; Decimal slippage_cost = 13;
}
message Position { string instrument_key = 1; int64 lots = 2; Decimal avg_price = 3; Decimal market_value = 4; }
message Portfolio { Decimal cash = 1; Decimal equity = 2; repeated Position positions = 3; }
message CommandResult { int64 seq = 1; bool accepted = 2; Reason reason = 3; string invalid_field = 4; repeated int64 order_ids = 5; }
message StepEvents { int64 step = 1; repeated Bar bars = 2; repeated Fill fills = 3; repeated Order changed_orders = 4; Portfolio portfolio = 5; }
enum SessionStatus { SESSION_STATUS_UNSPECIFIED = 0; RUNNING = 1; FINISHED_END = 2; BANKRUPT = 3; }

// Отчёт (ФТ-17). optional — значение может отсутствовать (мало данных).
message Metrics {
  double total_return = 1; double gross_return = 2; optional double cagr = 3; double max_drawdown = 4;
  int64 max_drawdown_steps = 5; optional double volatility = 6; optional double sharpe = 7; optional double sortino = 8;
  double turnover = 9; int64 fills = 10; int64 round_trips = 11; optional double win_rate = 12;
  int64 rejections = 13; int64 partial_fills = 14; double hhi_avg = 15; double max_position_share = 16;
  optional double benchmark_return = 17; int32 trading_days = 18;
}
message CostTotals { Decimal commission = 1; Decimal exchange_fee = 2; Decimal spread = 3; Decimal slippage = 4; }
message EquityPoint { int64 step = 1; Decimal equity = 2; }
message Finding { string code = 1; Level level = 2; string message = 3; int64 step = 4; }
message Report { Metrics metrics = 1; CostTotals costs = 2; repeated EquityPoint equity = 3; repeated Finding findings = 4; Level level = 5; Decimal final_equity = 6; }

message ReplaySessionRequest {
  MarketSpec market = 1; repeated JournalEntry journal = 2;
  int64 up_to_step = 3;        // курсор
  int64 events_from_step = 4;  // события шагов (events_from_step; up_to_step]; -1 — не нужны
  bool include_history = 5;    // все бары шагов [0; last_step]
  bool include_report = 6;
}
message ReplaySessionResponse {
  int64 total_steps = 1; SessionStatus status = 2; int64 last_step = 3;
  repeated StepEvents events = 4; repeated Bar history = 5; Portfolio portfolio = 6;
  repeated Order orders = 7; repeated Fill fills = 8; repeated CommandResult command_results = 9; Report report = 10;
}
message GetBarsRequest { MarketSpec market = 1; int64 from_step = 2; int64 to_step = 3; }
message GetBarsResponse { int64 total_steps = 1; repeated Bar bars = 2; }

// Стратегии (dsl.md).
message ParamValue { string name = 1; double value = 2; }
message StrategySource { string source = 1; repeated ParamValue params = 2; }
message TextEdit { int32 start_line = 1; int32 start_column = 2; int32 end_line = 3; int32 end_column = 4; string text = 5; }
message Diagnostic {
  string code = 1; Level level = 2; int32 start_line = 3; int32 start_column = 4; int32 end_line = 5; int32 end_column = 6;
  string message = 7; repeated TextEdit fix = 8;
}
message ParamDecl { string name = 1; double default_value = 2; bool has_range = 3; double min = 4; double max = 5; double step = 6; bool integer = 7; }
message CheckStrategyRequest { string source = 1; }
message CheckStrategyResponse { Level level = 1; repeated Diagnostic diagnostics = 2; repeated ParamDecl params = 3; }

// Прогоны (ФТ-14, 22, 23, 24).
message StressScenario { int64 start_step = 1 /* < 0 — середина периода */; Decimal gap_percent = 2; Decimal vol_multiplier = 3; int32 vol_bars = 4; Decimal volume_share = 5; }
enum CostFactor { COST_FACTOR_UNSPECIFIED = 0; NAIVE = 1; DELAY = 2; FEES = 3; SPREAD = 4; SLIPPAGE = 5; LIQUIDITY = 6; }
enum CostFlag { COST_FLAG_UNSPECIFIED = 0; COSTS_OVER_HALF_PROFIT = 1; SIGN_CHANGE = 2; SHARPE_OVER_3 = 3; }
message CostBreakdownStep { CostFactor factor = 1; Decimal net_result = 2; double net_return = 3; }
message CostBreakdown { repeated CostBreakdownStep steps = 1; repeated CostFlag flags = 2; }
enum RunStatus { RUN_STATUS_UNSPECIFIED = 0; COMPLETED = 1; BANKRUPT_STOP = 2; INVALID = 3; }
message RunResult {
  RunStatus status = 1; Level level = 2; Report report = 3; repeated Fill fills = 4; repeated Order orders = 5;
  CostBreakdown cost_breakdown = 6; fixed64 digest = 7; int64 last_step = 8; int64 total_steps = 9;
}
message RunProgress { int64 done_steps = 1; int64 total_steps = 2; }
message RunBacktestRequest { MarketSpec market = 1; StrategySource strategy = 2; StressScenario stress = 3; bool with_cost_breakdown = 4; }
message RunBacktestUpdate { oneof update { RunProgress progress = 1; RunResult result = 2; } }

message WalkForwardRequest { MarketSpec market = 1; string source = 2; int32 fit_days = 3; int32 test_days = 4; int32 shift_days = 5; int32 max_grid = 6; }
message WalkForwardSegment {
  int32 index = 1; string fit_from = 2; string fit_to = 3; string test_from = 4; string test_to = 5;
  repeated ParamValue chosen = 6; double fit_net_return = 7; RunResult test_result = 8;
}
message WalkForwardResult { repeated WalkForwardSegment segments = 1; double chained_return = 2; }
message WalkForwardUpdate { oneof update { RunProgress progress = 1; WalkForwardResult result = 2; } }

// Разбор расхождений (ФТ-18…20).
message AlgorithmRef { string id = 1; StrategySource strategy = 2; }
message DivergenceRequest { MarketSpec market = 1; repeated JournalEntry journal = 2; int64 last_step = 3; repeated AlgorithmRef algorithms = 4; }
enum DivergenceType { DIVERGENCE_TYPE_UNSPECIFIED = 0; EXCESS = 1; MISSED = 2; SIZE = 3; TIMING = 4; }
message Divergence {
  string algorithm_id = 1; string instrument_key = 2; DivergenceType type = 3;
  int64 human_step = 4; int64 algo_step = 5;          // -1 — нет действия
  int64 human_lots = 6; int64 algo_lots = 7;          // со знаком: + покупка, − продажа
  int64 horizon_step = 8; Decimal cost = 9; double cost_percent = 10; string reason = 11;
}
message MissedProfitableTrade { string instrument_key = 1; int64 entry_step = 2; int64 exit_step = 3; int64 lots = 4; Decimal net_pnl = 5; repeated string algorithm_ids = 6; }
message ConsensusItem { string instrument_key = 1; int64 step = 2; Side side = 3; bool human_action = 4; int32 agreeing = 5; int32 total = 6; Decimal median_cost = 7; }
message DivergenceResponse { repeated Divergence divergences = 1; repeated MissedProfitableTrade missed_profitable = 2; repeated ConsensusItem consensus = 3; repeated RunResult algorithm_portfolios = 4; }
```

Ошибки RPC: `INVALID_ARGUMENT` — неверная спецификация, ошибки DSL (в описании — коды диагностик через `;`); `FAILED_PRECONDITION` — нет данных снапшота на период; `INTERNAL` — нарушение целостности движка.

- [ ] Тест `ProtoContract.CompilesAndRoundTrips`: заполнить `ReplaySessionRequest` с одной записью журнала `place`, сериализовать, разобрать, сравнить поля; `Decimal{units=271, nano=350000000}` переживает round-trip.
- [ ] Заменить `simulation.proto`, добавить опции в `common.proto`; `scripts/dev.sh test` — PASS, `worker_tests` и `core_tests` зелёные (Ping не сломан).
- [ ] Коммит «gRPC-контракт: сессии, прогоны, стратегии, расхождения».

**Готово, когда:** CI `core` зелёный; файл совпадает с текстом выше (поправки — через issue этой задачи, до её закрытия).

### Задача 2: OpenAPI-контракт `openapi.yaml`

- **Репозиторий:** backend. **Размер:** M. **Волна:** 0.
- **Зависит от:** — (эндпоинты входа описываются так, как их делает задача 12).
- **Связано:** ADR-0002, ADR-0007, НФТ-6, ФТ-1…24, INV-7.

**Files:** Modify: `backend/api/openapi.yaml`. Test: `npx @redocly/cli lint api/openapi.yaml` в CI (добавляет задача 4) — здесь запуск вручную.

Общее: OpenAPI 3.1; ошибки — `application/problem+json`, схема `Problem {type, title, status, detail, code?, field?}` (`code` — машинный код: `INVALID_PARAMS`, `NO_PERIOD`, `TOO_MANY_BARS`, `SESSION_PLAYING`, `NOT_FOUND`, `FORBIDDEN`, `CONFLICT`, `DSL_ERRORS`, `TOO_LARGE`); деньги и цены — схема `Money` (строка, шаблон из «Глобальных ограничений»); id — `uuid`, кроме `orderId` (`int64`); все пути под `/api`, кроме служебных — с cookie-сессией и CSRF (`X-XSRF-TOKEN`).

Схемы (поле `?` — необязательное):

| Схема | Поля |
|---|---|
| `Timeframe` | enum `S1 S10 M1 M5 M10 M15 H1 D1` |
| `SessionStart` | `type: RANDOM \| DATE`, `date?: date`, `tickers?: string[1..5]` |
| `CreateSessionRequest` | `timeframe`, `durationDays: int` (одно из 20, 60, 120, 250), `instrumentCount?: int 1..5` (для RANDOM), `start: SessionStart` |
| `InstrumentView` | `key: "A".."E"`, `label` («Бумага A»), `sector`, `ticker?`, `name?`, `lotSize: int64`, `priceStep?: Money` — `ticker`, `name`, `priceStep` только в неслепой сессии |
| `BarView` | `step: int64`, `instrumentKey`, `day: int` (торговый день 1…N), `time?: date-time` (только неслепая), `open, high, low, close: Money`, `volume: string` (лоты; в слепой — относительный объём, 4 знака), `afterHalt: bool` |
| `PositionView` | `instrumentKey`, `lots: int64`, `avgPrice: Money`, `marketValue: Money` |
| `PortfolioView` | `cash`, `equity: Money`, `positions: PositionView[]` |
| `OrderView` | `id: int64`, `instrumentKey`, `side: BUY\|SELL`, `type: MARKET\|LIMIT\|STOP\|STOP_LIMIT\|TAKE_PROFIT\|TRAILING_STOP`, `lots`, `filledLots`, `limitPrice?`, `stopPrice?`, `trailingPercent?`, `trailingStopLevel?`, `ocoSiblingId?`, `timeInForce: DAY\|GTC`, `status: ACTIVE\|PARTIALLY_FILLED\|FILLED\|CANCELLED\|EXPIRED\|REJECTED`, `reason?: RejectReason`, `invalidField?`, `placedStep`, `ruleName?`, `because?` |
| `RejectReason` | enum = `Reason` из proto без `REASON_UNSPECIFIED` |
| `TradeView` | `orderId`, `instrumentKey`, `step`, `side`, `lots`, `price`, `value`, `commission`, `exchangeFee: Money`, `stopAndTakeSameBar: bool` |
| `SessionView` | `id`, `status: ACTIVE\|FINISHED`, `finishReason?: END\|BANKRUPT\|EARLY`, `playing: bool`, `speed: 1\|5\|10`, `cursor`, `totalSteps`, `blind: bool`, `timeframe`, `instruments[]`, `bars: BarView[]` (шаги 0…cursor), `portfolio`, `orders[]`, `trades[]`, `reveal?: Reveal` |
| `Reveal` | `periodFrom: date`, `periodTo: date`, `instruments: [{key, ticker, name}]` — только у завершённой |
| `SessionEvent` (SSE) | `oneOf`, дискриминатор `type`: `StepEvent {type: "step", cursor, bars[], portfolio, trades[], orders[] (изменённые)}`, `StateEvent {type: "state", status, playing, speed, cursor}`, `FinishedEvent {type: "finished", finishReason, reveal}` |
| `PlaceOrderRequest` | `clientOrderId: uuid`, `seenStep: int64`, `instrumentKey`, `side`, `type`, `lots: int64 ≥ 1`, `limitPrice?`, `stopPrice?`, `trailingPercent?`, `timeInForce`, `ocoWith?: OrderLeg` (`OrderLeg` = те же поля без `clientOrderId`, `seenStep`, `ocoWith`) |
| `CancelOrderRequest` | `clientOrderId: uuid`, `seenStep` |
| `ReplaceOrderRequest` | `clientOrderId: uuid`, `seenStep`, `order: OrderLeg`, `ocoWith?: OrderLeg` |
| `OrderPlacement` | `accepted: bool`, `orders: OrderView[]`, `reason?`, `invalidField?` |
| `Metrics` | поля proto `Metrics` в camelCase, `number`/`integer`, необязательные — nullable |
| `CostTotals` | `commission, exchangeFee, spread, slippage: Money` |
| `Report` | `subjectType: SESSION\|RUN`, `subjectId`, `level: OK\|WARNING\|ERROR`, `metrics`, `costs`, `finalEquity: Money`, `equity: [{step, equity: Money}]`, `findings: [{code, level, message, step}]`, `costBreakdown?: {steps: [{factor, netResult: Money, netReturn}], flags: [COSTS_OVER_HALF_PROFIT\|SIGN_CHANGE\|SHARPE_OVER_3]}`, `reveal?: Reveal`, `metadata: {snapshotId, snapshotFetchedAt, contentHash, timeframe, periodFrom, periodTo, instruments[], costs: {…: Money}, initialCash, strategyVersionId?, params?, stress?}` |
| `ParamDecl`, `Diagnostic`, `TextEdit` | поля proto в camelCase; `level: error\|warning` |
| `CheckResult` | `level: OK\|WARNING\|ERROR`, `diagnostics[]`, `params: ParamDecl[]` |
| `StrategySummary` | `id`, `name`, `hidden`, `deleted`, `updatedAt`, `latestVersion?: {id, number, published}` |
| `Strategy` | `StrategySummary` + `draftSource`, `forkedFrom?: {strategyId, versionId, versionNumber, sourceDeleted: bool}`, `versions: VersionSummary[]` |
| `VersionSummary` | `id`, `number`, `published`, `checkLevel`, `lintWarnings: int`, `createdAt` |
| `Version` | `VersionSummary` + `strategyId`, `strategyName`, `author` (имя или «Платформа»), `source`, `params`, `diagnostics` (рейтинга здесь нет: он в модуле analysis, отдельный эндпоинт) |
| `Rating` | `epochId`, `status: PENDING\|DONE\|INVALID`, `score?`, `byRegime: {UP\|DOWN\|FLAT: {score?, windows}}`, `medianSharpe?`, `medianMaxDrawdown?`, `profitableShare?`, `invalidReason?` |
| `CatalogItem` | `strategyId`, `name`, `author`, `latestVersion: {id, number}`, `rating?`, `lintWarnings` |
| `RunRequest` | `versionId`, `params: [{name, value}]`, `timeframe`, `durationDays: int ≥ 1`, `instrumentCount?`, `start: SessionStart`, `stress?: StressRequest` |
| `StressRequest` | `type: PARAMETRIC\|PRESET`, `preset?: FEB_2022\|MAR_2020`, `gapPercent?`, `volMultiplier?`, `volBars?`, `volumeShare?`, `startStep?` |
| `Run` | `id`, `status: QUEUED\|RUNNING\|DONE\|FAILED`, `runStatus?: COMPLETED\|BANKRUPT_STOP\|INVALID`, `level?`, `versionId`, `params`, `blind`, `progress: {done, total}`, `stressPairRunId?`, `repeatOf?`, `repeatMatches?: bool`, `digest?: string`, `error?`, `createdAt` |
| `RunEvent` (SSE) | `oneOf` по `type`: `ProgressEvent {type: "progress", done, total}`, `CompletedEvent {type: "completed", status, runStatus?}` |
| `WalkForwardRequest` | `versionId`, `timeframe`, `from: date`, `to: date`, `tickers: string[1..5]` |
| `WalkForward` | `id`, `status`, `progress`, `segments: [{index, fitFrom, fitTo, testFrom, testTo, chosenParams: [{name, value}], fitNetReturn, testRunId, testNetReturn}]`, `chainedReturn?` |
| `ComparisonRequest` | `versionIds: uuid[0..5]` (пусто — эталонная стратегия) |
| `Comparison` | `id`, `status: QUEUED\|RUNNING\|DONE\|FAILED`, `algorithms: [{versionId, name}]`, `divergences: [{versionId, instrumentKey, type: EXCESS\|MISSED\|SIZE\|TIMING, humanStep?, algoStep?, humanLots, algoLots, horizonStep, cost: Money, costPercent, reason}]`, `missedProfitable: [{instrumentKey, entryStep, exitStep, lots, netPnl, versionIds[]}]`, `consensus: [{instrumentKey, step, side, humanAction, agreeing, total, medianCost}]`, `totalCost: Money`, `algorithmReports: Report[]` |
| `HistoryItem` | `kind: SESSION\|RUN`, `id`, `createdAt`, `status`, `blind`, `mode: HUMAN\|ALGORITHM`, `title`, `netReturn?`, `finishReason?` |
| `DeletionRequest` | `id`, `strategyId`, `strategyName`, `reason`, `status: PENDING\|APPROVED\|REJECTED`, `comment?`, `createdAt` |
| `ReplayData` | `bars: BarView[]` (все, раскрытые), `trades[]`, `orders[]`, `instruments[]` (с тикерами), `totalSteps` |

Эндпоинты (тег = модуль, где контроллер):

| Метод и путь | Тег | Запрос → ответ |
|---|---|---|
| `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/me` | identity | как в задаче 12 |
| `GET /api/marketdata/timeframes` | marketdata | → `Timeframe[]` (есть данные в последнем готовом снапшоте) |
| `GET /api/marketdata/instruments` | marketdata | → `[{ticker, name, sector, from: date, to: date}]` |
| `POST /api/sessions` | sessions | `CreateSessionRequest` → 201 `SessionView`; 422 `NO_PERIOD`, `TOO_MANY_BARS` |
| `GET /api/sessions/{id}` | sessions | → `SessionView` |
| `GET /api/sessions/{id}/events` | sessions | → `text/event-stream` из `SessionEvent` |
| `POST /api/sessions/{id}/play` | sessions | `{speed: 1\|5\|10}` → `SessionView` |
| `POST /api/sessions/{id}/pause`, `POST /api/sessions/{id}/step` | sessions | → `SessionView`; `step` во время игры — 409 `SESSION_PLAYING` |
| `POST /api/sessions/{id}/orders` | sessions | `PlaceOrderRequest` → 201 `OrderPlacement` |
| `POST /api/sessions/{id}/orders/{orderId}/cancel` | sessions | `CancelOrderRequest` → `OrderPlacement` |
| `POST /api/sessions/{id}/orders/{orderId}/replace` | sessions | `ReplaceOrderRequest` → `OrderPlacement` |
| `POST /api/sessions/{id}/finish` | sessions | → `SessionView` (досрочно) |
| `GET /api/sessions/{id}/replay` | sessions | → `ReplayData`; 409, если сессия не завершена |
| `GET /api/sessions/{id}/report` | analysis | → `Report`; 404, пока нет |
| `POST /api/sessions/{id}/comparisons` | analysis | `ComparisonRequest` → 202 `Comparison` |
| `GET /api/comparisons/{id}` | analysis | → `Comparison` |
| `GET /api/history?blindOnly=bool&kind=SESSION\|RUN` | analysis | → `HistoryItem[]` (свои, новые первыми) |
| `GET /api/catalog?sort=score\|newest&regime=UP\|DOWN\|FLAT` | analysis | → `CatalogItem[]` |
| `GET /api/versions/{id}/rating` | analysis | → `Rating` (текущей эпохи); 404, если расчёта ещё не было |
| `GET /api/strategies` | workshop | → `StrategySummary[]` (свои) |
| `POST /api/strategies` | workshop | `{name, source?}` → 201 `Strategy` |
| `GET /api/strategies/{id}` | workshop | → `Strategy` |
| `PUT /api/strategies/{id}/draft` | workshop | `{source}` → `Strategy` |
| `POST /api/strategies/check` | workshop | `{source}` → `CheckResult` |
| `POST /api/strategies/{id}/versions` | workshop | → 201 `Version` (неизменяемая, неопубликованная); 422 `DSL_ERRORS` |
| `GET /api/versions/{id}` | workshop | → `Version` |
| `POST /api/versions/{id}/publish` | workshop | → `Version` |
| `POST /api/versions/{id}/fork` | workshop | `{name}` → 201 `Strategy` |
| `POST /api/strategies/{id}/hide`, `POST /api/strategies/{id}/unhide` | workshop | → `Strategy` |
| `POST /api/strategies/{id}/deletion-requests` | workshop | `{reason}` → 201 `DeletionRequest` |
| `GET /api/moderation/deletion-requests?status=PENDING` | workshop | → `DeletionRequest[]` (роль MODERATOR) |
| `POST /api/moderation/deletion-requests/{id}/approve`, `.../reject` | workshop | `{comment?}` → `DeletionRequest` |
| `POST /api/runs` | simulation | `RunRequest` → 202 `Run` (со стрессом — `Run` пары без стресса, `stressPairRunId` указывает на прогон со стрессом) |
| `GET /api/runs/{id}` | simulation | → `Run` |
| `GET /api/runs/{id}/events` | simulation | → `text/event-stream` из `RunEvent` |
| `GET /api/runs/{id}/report` | analysis | → `Report` |
| `POST /api/runs/{id}/repeat` | simulation | → 202 `Run` с `repeatOf` |
| `GET /api/runs/{id}/replay` | simulation | → `ReplayData`; 422 `TOO_LARGE`, если баров > 50 000 |
| `POST /api/walk-forwards` | simulation | `WalkForwardRequest` → 202 `WalkForward` |
| `GET /api/walk-forwards/{id}` | simulation | → `WalkForward` |

- [ ] Описать схемы и эндпоинты; у каждого эндпоинта — `operationId` (camelCase, глагол + сущность: `createSession`, `placeOrder`), `tags`, ответы ошибок `401`, `403`, `404`, `422` где применимо.
- [ ] `npx @redocly/cli lint api/openapi.yaml` — без ошибок.
- [ ] Коммит «OpenAPI: контракт REST и SSE для ФТ-1…24».

**Готово, когда:** файл проходит линтер; таблицы выше покрыты один к одному.

### Задача 3: Сборка `core`: области и флаги детерминизма

- **Репозиторий:** core. **Размер:** S. **Волна:** 1. **Зависит от:** 5, 34 (обе меняют те же CMake-файлы).
- **Связано:** INV-4.

**Files:** Modify: `core/CMakeLists.txt`, `core/src/core/CMakeLists.txt`, `core/tests/CMakeLists.txt`, `core/src/worker/CMakeLists.txt`, `core/AGENTS.md` («Структура»). Create: `core/src/core/<area>/CMakeLists.txt` и `core/tests/<area>/CMakeLists.txt` для каждой области, `core/tests/worker/CMakeLists.txt`, `core/tests/build/flags_test.cpp`, `core/testdata/README.md`. Modify: `core/src/core/money/CMakeLists.txt`, `core/tests/money/CMakeLists.txt` (на тот же glob).

- `src/core/CMakeLists.txt`: `foreach(area money market portfolio exec engine dsl run report analysis)` → `add_subdirectory(${area})`; в каждой области `file(GLOB CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/*.cpp)` → `target_sources(simulation_core PRIVATE …)`; `tests/<area>/CMakeLists.txt` — то же для `core_tests`; `tests/worker/CMakeLists.txt` — для `worker_tests` (`tests/worker_ping_test.cpp` остаётся на месте и в списке `worker_tests`); пустые области — `CMakeLists.txt` и `.gitkeep`.
- `src/worker/CMakeLists.txt`: `simulation_worker_lib` собирает `worker_service.cpp`, `file(GLOB CONFIGURE_DEPENDS handlers/*.cpp convert/*.cpp clickhouse/*.cpp)`.
- Флаги для `core_warnings`: GCC/Clang — `-ffp-contract=off`; проверка, что `-ffast-math` нигде не задан.
- `tests/support/*.cpp` (общие фикстуры, задача 7) входят и в `core_tests`, и в `worker_tests`; `testdata/` — файлы для тестов (DSL, эталонный портфель).

- [ ] Тест `BuildFlags.NoFusedMultiplyAdd`: `volatile double a = 1.0 + 0x1p-27, b = 1.0 - 0x1p-27, c = -1.0; EXPECT_EQ(a * b + c, 0.0);` — с FMA результат был бы −2⁻⁵⁴.
- [ ] Изменить CMake; `scripts/dev.sh test` — PASS, тесты Decimal, баров и Ping зелёные.
- [ ] Коммит «Сборка: автоподключение областей, -ffp-contract=off».

**Готово, когда:** CI `core` (оба job) зелёный; новая область подключается одним своим `CMakeLists.txt`.

### Задача 4: Фундамент backend: gRPC-клиент, контрактный тест, настройки

- **Репозиторий:** backend. **Размер:** M. **Волна:** 2. **Зависит от:** 1, 2, 12.
- **Связано:** ADR-0007, INV-6, INV-10, НФТ-6.

**Files:**
- Modify: `backend/build.gradle.kts` (плагин `com.google.protobuf`, `io.grpc:grpc-netty-shaded`, `grpc-protobuf`, `grpc-stub`, `grpc-inprocess` (test), `protobuf-java`, `com.clickhouse:clickhouse-jdbc` (classifier `all`), `com.atlassian.oai:swagger-request-validator-core`, `org.testcontainers:clickhouse`), `backend/src/main/resources/application.yml` (все ключи из «Соглашений»), `backend/.github/workflows/ci.yml` (шаги: проверка копии proto и линтер OpenAPI), `backend/src/main/java/ru/ttsc/lab/api/SecurityConfig.java` (`@EnableMethodSecurity`), `backend/AGENTS.md`.
- Create: `backend/scripts/sync-proto.sh`, `backend/src/main/proto/simulation.proto`, `backend/src/main/proto/common.proto` (копии), `backend/src/main/java/ru/ttsc/lab/config/{package-info,LabProperties}.java` (отдельный модуль `config` без зависимостей; `@ConfigurationProperties("lab")`, records на каждую группу, деньги и доли — `BigDecimal`), `backend/src/test/java/ru/ttsc/lab/api/OpenApiContractAssert.java`, `backend/src/test/java/ru/ttsc/lab/api/OpenApiContractAssertTest.java`.

Интерфейсы:
- `sync-proto.sh [путь-к-core]` (по умолчанию `../core`) копирует `proto/*.proto` в `src/main/proto/`; `--check` — выход 1 и diff, если копия отличается. CI делает `git clone --depth 1 https://github.com/tinkoff-trade-strategies-checking/core ../core && scripts/sync-proto.sh --check`.
- `OpenApiContractAssert.assertMatches(MvcResult result)` — проверяет запрос и ответ по `api/openapi.yaml` через `OpenApiInteractionValidator` (адаптер `MvcResult` → `SimpleRequest`/`SimpleResponse`), при нарушении — `AssertionError` со списком ошибок. Каждый тест контроллера в задачах 30–44 вызывает его на каждом ответе.
- `spring.flyway.out-of-order: true` в `application.yml`.

- [ ] Тест `OpenApiContractAssertTest.healthMatchesContract`: `GET /api/health` проходит; `nonContractPathFails` — ответ на путь, которого нет в контракте, даёт `AssertionError`.
- [ ] Тест `ProtoGenerationTest.decimalClassGenerated`: `pac.simulation.v1.Decimal.newBuilder().setUnits(1).build()` компилируется.
- [ ] Реализовать; `./gradlew build` — PASS (`ModularityTests`, `MoneyTypesArchTest` зелёные: генерированный код вне `ru.ttsc.lab`).
- [ ] Коммит «Фундамент: gRPC и proto, контрактный тест OpenAPI, настройки lab.*».

**Готово, когда:** CI `backend` зелёный, включая сверку proto с `core` и линтер OpenAPI.

### Задача 5: Decimal в C++ (уже в работе, task-list #8)

- **Репозиторий:** core. **Размер:** S. **Волна:** 0. **Зависит от:** —. **Связано:** ADR-0008, INV-6, НФТ-4.
- Выполняется в ветке `3-decimal`. План опирается на её интерфейс: `core::Decimal` (`fromUnits`, `fromUnitsNano`, `parse`, `toString(minFractionDigits)`, `toDouble`, `+ − unary−`, `times(int64)`, `mul/div(b, scale, RoundingMode)`, `mulDiv`, `round(scale, mode)`, `roundToStep(step, mode)`), `core::RoundingMode` (как `java.math.RoundingMode`), `core::fromProto/toProto` (`core/money/proto_conv.hpp`), `proto/common.proto` с `Decimal`.
- **Готово, когда:** влито в `main`; тесты из ветки зелёные.

### Задача 6: Фундамент frontend: клиент API, маршруты, SSE, общие части

- **Репозиторий:** frontend. **Размер:** M. **Волна:** 1. **Зависит от:** 2, 13, 63 (все трое меняют `package.json` и `app.*`).
- **Связано:** ADR-0007, ADR-0009, НФТ-6, INV-1, INV-7.

**Files:**
- Modify: `frontend/package.json`, `package-lock.json` (`ng-openapi-gen`, `codemirror`, `@codemirror/state`, `@codemirror/view`, `@codemirror/language`, `@codemirror/lint`), `frontend/angular.json` (если нужно), `frontend/src/app/app.routes.ts`, `frontend/src/app/app.config.ts`, `frontend/.github/workflows/ci.yml`, `frontend/.gitignore` (`src/app/core/api/generated/`), `frontend/AGENTS.md`, `frontend/api/README.md`.
- Create: `frontend/api/openapi.yaml` (копия), `frontend/scripts/sync-openapi.sh` (`--check` как в задаче 4, источник `../backend/api/openapi.yaml`), `frontend/ng-openapi-gen.json` (`input: api/openapi.yaml`, `output: src/app/core/api/generated`), npm-скрипты `generate:api` (вызывается в `prebuild`, `pretest`, `prestart`), `frontend/src/app/core/sse/event-stream.ts`, `frontend/src/app/shared/money.pipe.ts`, страницы-заглушки всех маршрутов ниже.

Маршруты (каждый — `loadComponent` на `features/<f>/<f>-page.ts`; фичу заполняет указанная задача):

| Путь | Фича | Задача |
|---|---|---|
| `login`, `register` | `auth` | 13 |
| `sessions/new` | `session-new` | 45 |
| `sessions/:id` | `arena` | 46, 47 |
| `sessions/:id/report`, `runs/:id/report` | `report` | 48 |
| `sessions/:id/comparisons/:comparisonId` | `comparison` | 49 |
| `sessions/:id/replay`, `runs/:id/replay` | `replay` | 50 |
| `history` | `history` | 51 |
| `workshop`, `workshop/:strategyId` | `workshop` | 53 |
| `versions/:versionId` | `version` | 55 |
| `catalog` | `catalog` | 56 |
| `runs/:id`, `walk-forwards/:id` | `run` | 57 |
| `moderation` | `moderation` | 58 |
| `''` → `history` | — | — |

Интерфейсы:
- `EventStream.connect<T>(url: string): { events: Signal<T | null>; status: Signal<'connecting' | 'open' | 'closed'>; close(): void }` — `EventSource` с `withCredentials`, разбор `JSON.parse(event.data)`; переподключение — встроенное в `EventSource`; при `status` → `open` после обрыва компонент перечитывает состояние по REST.
- `MoneyPipe` (`money`): строка `Money` → текст с пробелами в тысячах и запятой (`"1234567.5"` → `"1 234 567,50"`); арифметики над деньгами во frontend нет (INV-6).

- [ ] Тесты (Vitest): `money.pipe.spec.ts` — `"1234567.5"` → `"1 234 567,50"`, `"-0.01"` → `"−0,01"`, `"100"` → `"100,00"`; `event-stream.spec.ts` — фиктивный `EventSource` отдаёт `{"type":"step"}` → `events()` равен объекту, `close()` закрывает источник; `app.routes.spec.ts` — у каждого пути таблицы есть маршрут.
- [ ] Реализовать; `npm run lint && npm test && npm run build` — PASS.
- [ ] Коммит «Фундамент: клиент API из OpenAPI, маршруты всех экранов, SSE, деньги».

**Готово, когда:** CI `frontend` зелёный, включая `sync-openapi.sh --check`.

### Задача DI: Импорт данных и схема ClickHouse (уже в работе, task-list #6)

- **Репозиторий:** backend (`deploy/clickhouse/`, `tools/marketdata-import/`). **Волна:** 0. **Связано:** ФТ-3, ФТ-4, ФТ-5, INV-5.
- Схема (коммит `f5a4c6c` в ветке `3-marketdata-import`): `snapshots` / `snapshots_ready`, `securities` (`secid`, `name`, `sector`, `lot_size UInt32`, `price_step Decimal(18,6)`), `trading_calendar` (`date`, `is_trading`, `session_open`, `session_close`), `candles` (`interval_sec`, `ts_open`, OHLC `Decimal(18,6)`, `volume UInt64`, `available_at`), `trades`, параметризованный view `candles_from_trades(snapshot_id, interval_sec)`.
- Задачи 17, 34 и 62 читают ровно эти таблицы. По README импортёра: количество и объём — в штуках (ядро делит на `lot_size` вниз); фикстура — снапшот `ec6b3c97-7036-56cf-ba4d-ec4e919e682d` (`marketdata-import fixture`): SBER, GAZP, LKOH — минутные свечи 28–29.10.2026, дневные 19–30.10.2026, синтетические сделки `SYNTH`; IMOEX в фикстуре нет. Решение плана: сессия читает один `snapshot_id`; IMOEX, когда появится, — свечи `secid = 'IMOEX'`.

---

## Трек core

Все задачи трека: тесты GoogleTest в `tests/<area>/`, проверка — `scripts/dev.sh test` (PASS), коммит по-русски. Ниже в задачах эти три шага не повторяются: «Тесты» — что написать первым и убедиться, что падает; «Реализация» — что и где; «Готово, когда» — CI `core` зелёный и перечисленное.

### Задача 7: Шкала времени сессии и календарь

- **Размер:** M. **Волна:** 2. **Зависит от:** 3, 5, 34. **Связано:** ФТ-3, ФТ-5, ФТ-10, INV-1.

**Files:** Create: `src/core/include/core/market/{timeframe,instrument,step_bar,calendar_source,timeline}.hpp`, `src/core/market/{timeframe,timeline,in_memory_calendar_source}.cpp`, `tests/support/fixture1.{hpp,cpp}`, `tests/market/timeline_test.cpp`.

**Interfaces.** Consumes (задача 34): `core::Bar` (`index`, `tsOpenMs`, `availableAtMs`, OHLC, `volume` — штуки, `value`), `core::Security` (`secid`, `sector`, `lotSize`, `priceStep`), `core::BarRequest`, `core::BarSource`, `core::InMemoryBarSource`. Produces:

```cpp
namespace core {
enum class Timeframe { S1, S10, M1, M5, M10, M15, H1, D1 };
std::int32_t intervalSeconds(Timeframe);                       // 1, 10, 60, 300, 600, 900, 3600, 86400
struct Instrument { std::string key; std::string ticker; std::int64_t lotSize; Decimal priceStep; };
struct TradingDay { std::int32_t yyyymmdd; bool isTrading; };
class CalendarSource {
 public:
  virtual ~CalendarSource() = default;
  virtual std::vector<TradingDay> tradingDays(const std::string& snapshotId, std::int32_t fromYmd, std::int32_t toYmd) = 0;
};
class InMemoryCalendarSource : public CalendarSource { public: void add(const std::string& snapshotId, std::vector<TradingDay>); /* … */ };
struct StepBar { std::int64_t step; int instrument; std::int64_t timeUnixMs; std::int32_t tradingDay;
                 Decimal open, high, low, close; std::int64_t volumeLots; bool afterHalt; };
class Timeline {
 public:
  static Timeline build(std::vector<Instrument> instruments, const std::vector<std::vector<Bar>>& bars,
                        const std::vector<TradingDay>& calendar);
  static Timeline load(BarSource&, CalendarSource&, const std::string& snapshotId, std::vector<Instrument> instruments,
                       Timeframe, std::int32_t fromYmd, std::int32_t toYmd);   // московские даты включительно
  std::int64_t totalSteps() const;
  std::span<const StepBar> barsAt(std::int64_t step) const;      // по возрастанию instrument
  const StepBar* barOf(int instrument, std::int64_t step) const;  // nullptr, если бара нет
  const StepBar* lastBarOf(int instrument, std::int64_t upToStep) const;
  std::int32_t tradingDayOf(std::int64_t step) const;             // 1…N
  std::int32_t yyyymmddOf(std::int64_t step) const;
  bool isLastStepOfDay(std::int64_t step) const;
  std::int32_t tradingDays() const;
  Timeline slice(std::int32_t fromDay, std::int32_t toDay) const; // дни 1…N включительно, шаги перенумерованы с 0
  const std::vector<Instrument>& instruments() const;
  StepBar& mutableBar(std::int64_t step, int instrument);         // только для стресс-сценария (задача 26)
};
}
namespace core::testing {  // tests/support
struct Fixture { InMemoryBarSource bars; InMemoryCalendarSource calendar; std::vector<Instrument> instruments; std::string snapshotId; };
Fixture fixture1();
}
```

Правила:
- Шаги — отсортированное объединение `tsOpenMs` всех бумаг; на шаге у бумаги бар есть, только если у неё есть бар с этим временем. Бар шага становится видимым, только когда курсор дошёл до шага (после закрытия бара, ФТ-5); это держит движок (задача 15).
- Московская дата бара — `tsOpenMs` + 3 ч; `tradingDay` — номер даты среди различных дат шкалы, с 1.
- `volumeLots = volume / lotSize` с округлением вниз (объём в штуках — README импортёра DI).
- `afterHalt` (ФТ-5, предложение плана): у бумаги есть предыдущий бар и либо между их датами в календаре есть торговый день (`isTrading`), либо дата та же и разрыв ≥ 15 минут и ≥ 2 интервалов шага.
- `fixture1()` — снапшот `fixture-1`, шаг D1, торговые дни 2024-01-09…12, 15…19, 22 (10 дней; календарь 2024-01-08…22, выходные — `isTrading = false`): бумага A (лот 10, шаг 0.01) — close 100, 101, 103, 106, 104, 101, 99, 102, 105, 108, open = close предыдущего дня (первый — 100), high = max(open, close) + 1, low = min(open, close) − 1, объём 100 000 штук; бумага B (лот 10000, шаг 0.000005) — open = high = low = close = 0.0200, объём 10⁹ штук, бара 2024-01-12 нет. `tsOpenMs` — начало суток МСК в UTC, `availableAtMs` — плюс 24 ч.

**Тесты:**
- `Timeline.MergesInstrumentsByTime` (фикстура): `totalSteps() == 10`, `barOf(1, 3) == nullptr`, `barsAt(3).size() == 1`, бар B на шаге 4 — `afterHalt == true`.
- `Timeline.WeekendIsNotHalt`: бары A на шагах 3 и 4 (пятница и понедельник) — `afterHalt == false`.
- `Timeline.IntradayGap`: шаг M1, разрыв 20 минут внутри дня → `afterHalt == true`; 3 минуты → `false`.
- `Timeline.VolumeInLots`: `volume = 12345`, `lotSize = 10` → `volumeLots == 1234`.
- `Timeline.SliceRenumbersSteps`: `slice(3, 5)` — 3 шага, первый `step == 0`, `tradingDayOf(0) == 1`.
- `Timeline.LoadUsesSources`: `load(fixture.bars, fixture.calendar, "fixture-1", …, D1, 20240109, 20240122)` — 10 шагов.

### Задача 8: Портфель и сделки «покупка → продажа»

- **Размер:** S. **Волна:** 2. **Зависит от:** 3, 5. **Связано:** ФТ-10, ФТ-17, ФТ-20, INV-6.

**Files:** Create: `src/core/include/core/portfolio/portfolio.hpp`, `src/core/portfolio/portfolio.cpp`, `tests/portfolio/portfolio_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
enum class Side { Buy, Sell };
struct RoundTrip { int instrument; std::int64_t entryStep, exitStep, entryOrderId, lots; Decimal entryValue, exitValue, costs, netPnl; };
class Portfolio {
 public:
  Portfolio(Decimal initialCash, std::size_t instrumentCount);
  const Decimal& cash() const;
  std::int64_t lots(int instrument) const;
  Decimal avgPrice(int instrument) const;                  // 0, если позиции нет
  void applyFill(int instrument, Side side, std::int64_t lots, const Decimal& price, const Decimal& value,
                 const Decimal& commission, const Decimal& fee, std::int64_t step, std::int64_t orderId);
  static Decimal positionValue(std::int64_t lots, std::int64_t lotSize, const Decimal& close);  // до копейки HALF_UP
  Decimal equity(const std::vector<std::optional<Decimal>>& lastClose, const std::vector<std::int64_t>& lotSizes) const;
  const std::vector<RoundTrip>& roundTrips() const;
};
}
```

Правила: покупка — `cash −= value + commission + fee`; продажа — `cash += value − commission − fee`; продажа больше позиции — `std::logic_error` (проверки — в исполнении). Средняя цена покупки — взвешенная, 9 знаков HALF_UP; при нулевой позиции сбрасывается. Пары покупка → продажа — по FIFO: на каждую сопоставленную часть `entryValue = value_buy · m / lots_buy`, `exitValue = value_sell · m / lots_sell`, `costs` — так же пропорционально из комиссий и сборов обеих сделок, всё до копейки HALF_UP; `netPnl = exitValue − entryValue − costs`.

**Тесты:**
- `Portfolio.BuyThenSellRoundTrip`: капитал 1 000 000; покупка 100 лотов по 271.54 (сумма 271540.00, комиссия 135.77, сбор 27.16) → `cash == 728297.07`; продажа 100 по 274.03 (сумма 274030.00, комиссия 137.02, сбор 27.41) → `cash == 1002162.64`, одна пара, `netPnl == 2162.64`.
- `Portfolio.AvgPriceWeighted`: покупки 100 лотов по 271.54 и 50 по 268.91 → `avgPrice == 270.663333333`.
- `Portfolio.PositionValueHalfUp`: 3 лота × 10 × 0.0245 → `0.74` (0.735 → HALF_UP).
- `Portfolio.SellMoreThanPositionThrows`.

### Задача 9: DSL: лексер и парсер

- **Размер:** M. **Волна:** 2. **Зависит от:** 3. **Связано:** ФТ-12, ФТ-14, `dsl.md` («Лексика», «Грамматика»).

**Files:** Create: `src/core/include/core/dsl/{ast,diagnostic,parser}.hpp`, `src/core/dsl/{lexer,parser}.cpp`, `tests/dsl/parser_test.cpp`, `testdata/dsl/reference.lab` (эталонная стратегия из `dsl.md`).

**Interfaces (Produces):**

```cpp
namespace core::dsl {
struct SourceRange { int startLine, startColumn, endLine, endColumn; };   // с 1, столбцы — в кодовых точках UTF-8
enum class Level { Ok, Warning, Error };
struct TextEdit { SourceRange range; std::string text; };
struct Diagnostic { std::string code; Level level; SourceRange range; std::string message; std::vector<TextEdit> fix; };
struct Expr;  using ExprPtr = std::unique_ptr<Expr>;
struct Offset { bool negative; std::variant<std::int64_t, std::string> value; SourceRange range; };
struct Number { double value; std::string text; };  struct Bool { bool value; };  struct Na {};
struct Ident { std::string name; std::optional<Offset> offset; };
struct Call { std::string name; std::vector<ExprPtr> args; std::optional<Offset> offset; };
struct Unary { char op; ExprPtr operand; };                                   // '-' или '!' (not)
struct Binary { std::string op; ExprPtr left, right; };                       // "or" "and" "<" … "+" "-" "*" "/"
struct Expr { std::variant<Number, Bool, Na, Ident, Call, Unary, Binary> node; SourceRange range; };
struct StringTemplate { std::vector<std::variant<std::string, ExprPtr>> parts; SourceRange range; };
enum class SizeKind { Lots, PercentEquity, PercentCash, PercentPosition, All };
enum class OrderKind { Market, Limit, Stop, TakeProfit };
struct Action { enum class Kind { Buy, Sell, Cancel } kind; SizeKind sizeKind; ExprPtr size; OrderKind orderKind;
                ExprPtr price; std::optional<bool> day; SourceRange range; };
struct ParamDecl { std::string name; double value; std::optional<double> min, max, step; SourceRange range; };
struct Rule { std::string name; ExprPtr when; Action action; StringTemplate because; SourceRange range; };
struct Program { std::vector<ParamDecl> params; std::vector<Rule> rules; };
struct ParseResult { std::optional<Program> program; std::vector<Diagnostic> diagnostics; };
ParseResult parse(std::string_view source);
}
```

Правила: грамматика — ровно EBNF из `dsl.md`; при первой синтаксической ошибке разбор останавливается, диагностика `E-SYN` с местом и ожидаемым токеном («ожидалось `then`»). Ограничения `dsl.md` (64 КиБ, 100 правил, 50 параметров) — тоже `E-SYN`.

**Тесты:**
- `Parser.ParsesReferenceStrategy`: `testdata/dsl/reference.lab` → 6 параметров, 4 правила, у правила «стоп» `orderKind == Stop`.
- `Parser.NegativeOffsetIsSyntacticallyValid`: `when close[-1] > close then buy 10 lots because "x"` → программа есть, `offset->negative == true`.
- `Parser.MissingThen`: `rule "a" when close > open buy 1 lots because "x"` → `E-SYN` «ожидалось `then`» в строке 1, столбце 28.
- `Parser.StringInterpolation`: `"RSI = {rsi(close, 14)}, {{x}}"` → части: текст `"RSI = "`, выражение, текст `", {x}"`.
- `Parser.Precedence`: `a or b and not c < 1 + 2 * 3` разбирается как `a or (b and (not (c < (1 + (2 * 3)))))`.

### Задача 10: Индикаторы

- **Размер:** S. **Волна:** 2. **Зависит от:** 3. **Связано:** ФТ-12, `dsl.md` («Функции»), INV-4.

**Files:** Create: `src/core/include/core/dsl/indicators.hpp`, `src/core/dsl/indicators.cpp`, `tests/dsl/indicators_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core::dsl {
using Value = std::optional<double>;   // nullopt — na
class Indicator { public: virtual ~Indicator() = default; virtual Value update(const std::vector<Value>& inputs) = 0; };
std::unique_ptr<Indicator> makeIndicator(std::string_view name, const std::vector<std::int64_t>& intArgs);
// имена: sma ema rsi stdev highest lowest change (входы: x); atr (входы: high, low, close); crossover crossunder (входы: a, b)
}
```

Правила — формулы `dsl.md`; на входе `na` — состояние не меняется, результат `na`.

**Тесты** (ряд `close = 10, 11, 12, 11, 13, 14, 13, 15, 16, 15`, `high = close + 1`, `low = close − 1`, n = 3, сравнение с допуском 1e-9):
- `sma`: `na, na, 11, 11.3333333333, 12, 12.6666666667, 13.3333333333, 14, 14.6666666667, 15.3333333333`.
- `ema`: `na, na, 11, 11, 12, 13, 13, 14, 15, 15`.
- `rsi`: `na, na, na, 66.6666666667, 83.3333333333, 87.8787878788, 62.3655913978, 79.8850574713, 85.0905218317, 61.2965093978`.
- `atr`: `na, na, 2, 2, 2.3333333333, 2.2222222222, 2.1481481481, 2.4320987654, 2.2880658436, 2.1920438957`.
- `stdev`: `na, na, 0.8164965809, 0.4714045208, 0.8164965809, 1.2472191289, 0.4714045208, 0.8164965809, 1.2472191289, 0.4714045208`.
- `crossover(a, b)` на `a = 1, 2, 3`, `b = 2, 2, 2` → `false, false, true`; `rsi` при одних ростах → 100, при постоянном ряде → 50.

### Задача 11: Исполнение рыночных заявок

- **Размер:** M. **Волна:** 3. **Зависит от:** 7, 8. **Связано:** ФТ-7, ФТ-8, ФТ-9, ФТ-10, INV-2, INV-3, INV-6, `decisions.md` («Модель исполнения», «Заявки», «Деньги и округление»).

**Files:** Create: `src/core/include/core/exec/{order,costs,execution}.hpp`, `src/core/exec/{costs,validation,execution,market_orders}.cpp`, `tests/exec/{costs_test,validation_test,market_orders_test}.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
enum class OrderType { Market, Limit, Stop, StopLimit, TakeProfit, TrailingStop };
enum class TimeInForce { Day, Gtc };
enum class OrderStatus { Active, PartiallyFilled, Filled, Cancelled, Expired, Rejected };
enum class Reason { None, InvalidParams, InsufficientCash, InsufficientPosition, SessionNotActive, OrderNotActive,
                    LiquidityLimit, OcoSiblingFilled, PositionClosed, Replaced, SessionEnd, CancelledByUser, RuleReplaced, DayExpired };
struct OrderSpec { int instrument; Side side; OrderType type; std::int64_t lots;
                   std::optional<Decimal> limitPrice, stopPrice, trailingPercent; TimeInForce tif; };
struct Order { std::int64_t id; OrderSpec spec; std::int64_t placedStep; OrderStatus status; Reason reason;
               std::string invalidField; std::int64_t filledLots; std::int64_t ocoSiblingId; std::string ruleName, because;
               std::optional<Decimal> trailingPeak, trailingStopLevel; bool triggered; std::int64_t closedStep; };
struct Fill { std::int64_t orderId, step; int instrument; Side side; std::int64_t lots;
              Decimal price, basePrice, value, commission, fee, spreadCost, slippageCost; bool stopAndTakeSameBar; };
struct CostConfig { Decimal commissionRate, exchangeFeeRate, spread, slippageKappa;
                    std::optional<Decimal> liquidityShare;     // nullopt — без лимита (только для ФТ-24)
                    static CostConfig defaults(); static CostConfig zero(); };
struct Validation { bool ok; Reason reason; std::string field; };
Decimal fillPrice(Side, const Decimal& base, std::int64_t lots, std::int64_t barVolumeLots, const CostConfig&, const Decimal& priceStep);
struct Amounts { Decimal value, commission, fee; };
Amounts amounts(const Decimal& price, std::int64_t lots, std::int64_t lotSize, const CostConfig&);
class ExecutionEngine {
 public:
  ExecutionEngine(std::vector<Instrument> instruments, CostConfig costs, bool naive);
  Validation validate(const OrderSpec&, const Portfolio&, const Timeline&, std::int64_t step) const;
  // исполняет активные заявки на барах шага step; меняет orders и portfolio, дописывает fills и id изменённых заявок
  void processStep(std::int64_t step, const Timeline&, std::vector<Order>& orders, Portfolio&,
                   std::vector<Fill>& fills, std::vector<std::int64_t>& changed) const;
  void processNaive(std::int64_t step, const Timeline&, std::vector<Order>& orders, Portfolio&,
                    std::vector<Fill>& fills, std::vector<std::int64_t>& changed) const;   // ФТ-24: по close бара решения
};
}
```

Алгоритмы (точно):
- `fillPrice`: `frac = κ · lots / V` (деление — 9 знаков HALF_UP); покупка `m = 1 + s/2 + frac`, продажа `m = 1 − s/2 − frac`; `raw = base · m` (9 знаков HALF_UP); итог — `raw.roundToStep(priceStep, CEILING)` для покупки, `FLOOR` для продажи.
- `amounts`: `value = (price · lots · lotSize).round(2, HALF_UP)`; `commission = (value · commissionRate).round(2, CEILING)`; `fee = (value · exchangeFeeRate).round(2, CEILING)`.
- `spreadCost = (base · s/2 · lots · lotSize).round(2, HALF_UP)`; `slippageCost = (|price − base| · lots · lotSize).round(2, HALF_UP) − spreadCost`.
- Рыночная заявка, поданная на шаге s, исполняется на первом шаге > s, где у её бумаги есть бар, по `base = open`. Бюджет ликвидности бумаги на шаге — `floor(p · V)` лотов на все заявки шага. Количество q = min(остаток, бюджет; для продажи — позиция). Покупка: если `value + commission + fee > cash`, q уменьшается до наибольшего, при котором хватает денег (двоичный поиск по q, цена пересчитывается для каждого q). q = 0 — заявка снимается с причиной ограничивающего фактора; остаток после частичного исполнения снимается с той же причиной (`LIQUIDITY_LIMIT`, `INSUFFICIENT_CASH`, `INSUFFICIENT_POSITION`); статус — `Cancelled` с `filledLots > 0` (частичное исполнение) либо `Filled`.
- `validate` (при подаче, по close последнего бара бумаги не позже шага): `lots ≥ 1`; для типов с лимитом — `limitPrice > 0`; со стопом — `stopPrice > 0`; `trailingPercent ∈ (0; 50]`; `TakeProfit` и `TrailingStop` — только продажа; стоп на покупку выше последнего close, на продажу — ниже; тейк-профит выше последнего close. Иначе `InvalidParams` с полем (`lots`, `limitPrice`, `stopPrice`, `trailingPercent`, `side`). Покупка: `lots · lotSize · цена · (1 + commissionRate + exchangeFeeRate) > cash` → `InsufficientCash` (цена — `limitPrice` для лимитных, иначе последний close). Продажа: `lots > позиция` → `InsufficientPosition`.
- В этой задаче `processStep` исполняет только `Market`; прочие типы остаются `Active` (их добавляет задача 14).
- `naive`: `processNaive` исполняет рыночные заявки шага s по close последнего бара бумаги не позже s, без издержек, спреда, проскальзывания и лимита ликвидности.

**Тесты** (бумага A: лот 10, шаг 0.01; бумага B: лот 10000, шаг 0.000005; издержки по умолчанию):
- `Costs.FillPriceBuyA`: base 271.35, 100 лотов, V = 50000 → `frac = 0.0002`, `raw = 271.539945`, цена `271.54`; `amounts` → 271540.00 / 135.77 / 27.16.
- `Costs.FillPriceBuyB`: base 0.0245, 300 лотов, V = 90000 → `frac = 0.000333333`, `raw = 0.024520417`, цена `0.024525`; 73575.00 / 36.79 / 7.36.
- `Costs.FillPriceSellA`: base 275.00, 30 лотов, V = 1000 → `raw = 274.0375`, цена `274.03`; 82209.00 / 41.11 / 8.23.
- `MarketOrders.NotBeforeNextBar` (INV-2): заявка на шаге 0 → исполнение на шаге 1 по open шага 1; на шаге 0 исполнений нет.
- `MarketOrders.WaitsForOwnInstrumentBar` (ревью, п. 3): у B нет бара на шаге 3, заявка B на шаге 2 исполняется на шаге 4.
- `MarketOrders.ZeroLiquidityBudget` (ревью, п. 4): V = 9 лотов → `floor(0.1 · 9) = 0` → `Cancelled`, `LiquidityLimit`, исполнений нет.
- `MarketOrders.PartialByLiquidity`: заявка 300 лотов, V = 2000 → исполнено 200, статус `Cancelled`, `filledLots == 200`, причина `LiquidityLimit`.
- `MarketOrders.ReducedByCash`: денег на 3 лота с издержками → исполнено 3, остаток `InsufficientCash`.
- `Validation.StopWrongSide`: стоп на продажу выше последнего close → `InvalidParams`, поле `stopPrice`.

### Задача 14: Условные заявки: лимит, стоп, стоп-лимит, тейк-профит, трейлинг, OCO, срок «день»

- **Размер:** M. **Волна:** 4. **Зависит от:** 11. **Связано:** ФТ-7, ФТ-9, INV-2, `decisions.md` («Исполнение», «Заявки»).

**Files:** Create: `src/core/exec/conditional_orders.cpp`, `tests/exec/conditional_orders_test.cpp`. Modify: `src/core/exec/execution.cpp` (вызов обработки условных заявок).

Правила на баре b (b > шага подачи) бумаги заявки; O, H, L — цены бара; порядок обработки на шаге: рыночные → стоп-типы (стоп, сработавший стоп-лимит не исполняется на баре срабатывания, трейлинг) → лимитные и тейк-профит; внутри группы — по `id`:
- Лимит на покупку L: исполняется, если `O ≤ L` или `low < L` (строго: касание уровня не исполняет); цена — `min(L, fillPrice(Buy, O, …))`, если `O ≤ L`, иначе `L`. Продажа — зеркально (`O ≥ L` или `high > L`; цена `max(L, fillPrice(Sell, O, …))` или `L`). Бюджет ликвидности общий; остаток остаётся активным (`PartiallyFilled`).
- Стоп на покупку S: срабатывает, если `O ≥ S` или `high ≥ S`; исполняется на этом же баре как рыночная от `base = max(O, S)`. На продажу: `O ≤ S` или `low ≤ S`, `base = min(O, S)`. Остаток сверх ликвидности снимается (`LiquidityLimit`).
- Стоп-лимит: срабатывание — как у стопа; с бара b+1 действует как лимитная с `limitPrice`.
- Тейк-профит (только продажа) T: как лимитная продажа с ценой T.
- Трейлинг-стоп (только продажа), d %: пик при подаче — close бара подачи; после каждого бара пик = max(пик, high); уровень для следующего бара = `(пик · (1 − d/100)).roundToStep(priceStep, FLOOR)`; срабатывание и цена — как у стопа на продажу с S = уровень.
- OCO: исполнение (любого объёма) одной ноги снимает другую (`OcoSiblingFilled`); отмена одной ноги снимает обе.
- ФТ-9: если на баре сработал стоп-тип на продажу и на этом же баре сработал бы тейк-профит или лимит на продажу той же бумаги, сделка стопа помечается `stopAndTakeSameBar`, тейк исполняется только на остаток позиции.
- Срок `Day`: заявка снимается (`Expired`, `DayExpired`) после обработки последнего шага торгового дня своего первого допустимого шага (s + 1).

**Тесты** (бумага: лот 10, шаг 0.01; 10 лотов; V = 1000, т. е. `frac = 0.001`):
- `Limit.BuyOpensBelowLimit`: L = 100.00, O = 99.00 → `raw = 99.1485`, цена `99.15`.
- `Limit.BuyTouchedNotCrossed`: L = 100.00, O = 101, low = 100.00 → не исполнена; low = 99.99 → цена `100.00`.
- `Stop.SellTriggeredIntraBar`: S = 95, O = 96, low = 94 → base 95, `raw = 94.8575`, цена `94.85`.
- `Stop.SellGapDown`: S = 95, O = 90 → base 90, `raw = 89.865`, цена `89.86`.
- `Trailing.FollowsPeak`: d = 5 %, close подачи 100; бар 1: high 110, low 99 → не срабатывает (уровень 95.00), новый уровень `104.50`; бар 2: O = 106, low = 104 → срабатывает, base 104.50, `raw = 104.34325`, цена `104.34`.
- `Oco.FillCancelsSibling`, `Oco.CancelOneCancelsBoth`.
- `StopBeforeTake.SameBar` (ФТ-9): позиция 10 лотов, стоп 95 и тейк 110 на одном баре (high 111, low 94) → исполнен стоп, флаг `true`, тейк снят без исполнения.
- `Day.ExpiresEndOfFirstDay`: дневная лимитная заявка, поданная на последнем шаге дня 1, действует весь день 2 и снимается после его последнего шага.

### Задача 15: Движок сессии: проигрывание журнала

- **Размер:** M. **Волна:** 4. **Зависит от:** 11. **Связано:** ФТ-6, ФТ-10, ФТ-11, НФТ-1, НФТ-5, INV-1, INV-2, INV-8.

**Files:** Create: `src/core/include/core/engine/{journal,session_engine}.hpp`, `src/core/engine/session_engine.cpp`, `tests/engine/session_engine_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
struct PlaceCmd { OrderSpec order; std::optional<OrderSpec> ocoWith; };
struct CancelCmd { std::int64_t orderId; Reason reason = Reason::CancelledByUser; };
struct ReplaceCmd { std::int64_t orderId; PlaceCmd replacement; };
struct JournalEntry { std::int64_t seq; std::int64_t step; std::variant<PlaceCmd, CancelCmd, ReplaceCmd> command;
                      std::string ruleName, because; };                     // правило и причина — только у стратегии
struct CommandResult { std::int64_t seq; bool accepted; Reason reason; std::string field; std::vector<std::int64_t> orderIds; };
struct PortfolioSnapshot { Decimal cash, equity; std::vector<std::int64_t> lots; std::vector<Decimal> avgPrice, marketValue; };
struct StepEvents { std::int64_t step; std::vector<StepBar> bars; std::vector<Fill> fills; std::vector<Order> changedOrders; PortfolioSnapshot portfolio; };
struct EquityPoint { std::int64_t step; Decimal equity; };
enum class SessionStatus { Running, FinishedEnd, Bankrupt };
struct SessionSpec { std::vector<Instrument> instruments; CostConfig costs; Decimal initialCash; bool naive = false; };
struct IntegrityViolation : std::logic_error { using std::logic_error::logic_error; };  // бар позже текущего шага, исполнение не позже шага подачи
class SessionEngine {                                   // копируемый: копия — снимок состояния (нужно задаче 29)
 public:
  SessionEngine(SessionSpec spec, std::shared_ptr<const Timeline> timeline);
  CommandResult apply(const JournalEntry& entry);       // entry.step == currentStep(), иначе std::invalid_argument
  void advance();                                       // обработать шаг currentStep() + 1
  std::int64_t currentStep() const;  SessionStatus status() const;
  const Portfolio& portfolio() const;  const std::vector<Order>& orders() const;  const std::vector<Fill>& fills() const;
  const std::vector<EquityPoint>& equity() const;       // по шагу на каждый пройденный шаг, с 0
  StepEvents lastStepEvents() const;
  PortfolioSnapshot snapshot() const;
};
struct ReplayResult { SessionStatus status; std::int64_t lastStep; std::vector<StepEvents> events;
                      std::vector<CommandResult> commandResults; SessionEngine engine; };
ReplayResult replaySession(const SessionSpec&, std::shared_ptr<const Timeline>, std::span<const JournalEntry> journal,
                           std::int64_t upToStep, std::int64_t eventsFromStep);
}
```

Порядок (точно): курсор начинается с 0 (на шаге 0 заявок нет, стоимость = капитал). Для k = 0…: применить записи журнала с `step == k` по `seq` (проверка — `ExecutionEngine::validate`; отклонённая запись создаёт заявку в статусе `Rejected` с причиной); в наивном режиме — `processNaive(k)`; если k = upToStep — стоп; иначе `advance()`: `processStep(k+1)`, переоценка по последним close, снятие дневных заявок, если шаг последний в дне; `equity ≤ 0` → `Bankrupt`, `lastStep = k+1`; если k+1 = `totalSteps − 1` — после обработки все активные заявки снимаются (`SessionEnd`), статус `FinishedEnd`. `id` заявки = `seq · 2 + нога`. Замена: сначала проверяется новая заявка; не прошла — запись отклонена целиком (`accepted = false`), старая не тронута. Записи с невозрастающим `step` или `step > upToStep` — `std::invalid_argument`.

**Тесты** (фикстура `core::testing::fixture1()`):
- `Replay.NoFutureBars` (INV-1): `upToStep = 3` → ни в `events`, ни где-либо в результате нет бара со `step > 3`.
- `Replay.OrderExecutesNextBar` (INV-2): покупка на шаге 2 → исполнение со `step == 3`.
- `Replay.Deterministic` (INV-8): один журнал из 6 записей, проигранный до шага 9 целиком и «по шагам» (upToStep = 0…9, каждый раз заново) → одинаковые `fills`, `orders`, `equity`.
- `Replay.RejectedStillJournaled`: продажа без позиции → `accepted = false`, `InsufficientPosition`, заявка `Rejected`.
- `Replay.ReplaceAtomic`: замена с некорректной новой заявкой → старая активна.
- `Replay.FinishedEndCancelsOrders`: лимитная заявка, не исполненная до конца, → `Cancelled`, `SessionEnd`, статус `FinishedEnd`.
- `Replay.EquitySeriesLength`: `equity().size() == lastStep + 1`.

### Задача 16: Эталонный портфель (INV-6)

- **Размер:** S. **Волна:** 4. **Зависит от:** 11. **Связано:** INV-6, НФТ-4, ТЗ («ручные примеры сходятся»).

**Files:** Create: `tests/exec/reference_portfolio_test.cpp`, `testdata/reference-portfolio.md` (таблица ниже).

Тест вызывает `fillPrice`, `amounts`, `Portfolio::applyFill` для 19 сделок и сверяет каждую строку. Бумага A: лот 10, шаг 0.01; B: лот 10000, шаг 0.000005; капитал 1 000 000.00; издержки по умолчанию. Таблица посчитана независимой реализацией правил `decisions.md` (Python `decimal`):

| # | Бумага | Сторона | Лоты | O | V | κq/V | O·m | Цена | Сумма | Комиссия | Сбор | Деньги после | Позиция | Средняя |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | BUY | 100 | 271.35 | 50000 | 0.0002 | 271.539945 | 271.54 | 271540.00 | 135.77 | 27.16 | 728297.07 | 100 | 271.54 |
| 2 | A | BUY | 50 | 268.10 | 2000 | 0.0025 | 268.9043 | 268.91 | 134455.00 | 67.23 | 13.45 | 593761.39 | 150 | 270.663333333 |
| 3 | B | BUY | 300 | 0.0245 | 90000 | 0.000333333 | 0.024520417 | 0.024525 | 73575.00 | 36.79 | 7.36 | 520142.24 | 300 | 0.024525 |
| 4 | A | SELL | 30 | 275.00 | 1000 | 0.003 | 274.0375 | 274.03 | 82209.00 | 41.11 | 8.23 | 602301.90 | 120 | 270.663333333 |
| 5 | B | BUY | 1200 | 0.0251 | 20000 | 0.006 | 0.02526315 | 0.025265 | 303180.00 | 151.59 | 30.32 | 298939.99 | 1500 | 0.025117 |
| 6 | A | BUY | 7 | 262.47 | 70 | 0.01 | 265.225935 | 265.23 | 18566.10 | 9.29 | 1.86 | 280362.74 | 127 | 270.363858267 |
| 7 | B | SELL | 500 | 0.0262 | 60000 | 0.000833333 | 0.026165067 | 0.026165 | 130825.00 | 65.42 | 13.09 | 411109.23 | 1000 | 0.025117 |
| 8 | A | SELL | 127 | 280.99 | 4000 | 0.003175 | 279.95736175 | 279.95 | 355536.50 | 177.77 | 35.56 | 766432.40 | 0 | — |
| 9 | B | SELL | 1000 | 0.0240 | 1000000 | 0.0001 | 0.0239856 | 0.023985 | 239850.00 | 119.93 | 23.99 | 1006138.48 | 0 | — |
| 10 | A | BUY | 250 | 250.00 | 2500 | 0.01 | 252.625 | 252.63 | 631575.00 | 315.79 | 63.16 | 374184.53 | 250 | 252.63 |
| 11 | A | SELL | 100 | 249.99 | 100000 | 0.0001 | 249.840006 | 249.84 | 249840.00 | 124.92 | 24.99 | 623874.62 | 150 | 252.63 |
| 12 | B | BUY | 2000 | 0.0199 | 25000 | 0.008 | 0.02006915 | 0.02007 | 401400.00 | 200.70 | 40.14 | 222233.78 | 2000 | 0.02007 |
| 13 | A | BUY | 1 | 301.13 | 10 | 0.01 | 304.291865 | 304.30 | 3043.00 | 1.53 | 0.31 | 219188.94 | 151 | 252.97218543 |
| 14 | A | SELL | 151 | 310.50 | 3000 | 0.005033333 | 308.781900104 | 308.78 | 466257.80 | 233.13 | 46.63 | 685166.98 | 0 | — |
| 15 | B | SELL | 999 | 0.0303 | 9990 | 0.01 | 0.02998185 | 0.02998 | 299500.20 | 149.76 | 29.96 | 984487.46 | 1001 | 0.02007 |
| 16 | B | BUY | 1 | 0.0310 | 10 | 0.01 | 0.0313255 | 0.03133 | 313.30 | 0.16 | 0.04 | 984173.96 | 1002 | 0.020081238 |
| 17 | A | BUY | 40 | 255.55 | 400 | 0.01 | 258.233275 | 258.24 | 103296.00 | 51.65 | 10.33 | 880815.98 | 40 | 258.24 |
| 18 | B | SELL | 502 | 0.0288 | 50000 | 0.001004 | 0.028756685 | 0.028755 | 144350.10 | 72.18 | 14.44 | 1025079.46 | 500 | 0.020081238 |
| 19 | A | SELL | 20 | 257.77 | 800 | 0.0025 | 256.99669 | 256.99 | 51398.00 | 25.70 | 5.14 | 1076446.62 | 20 | 258.24 |

Итог: деньги 1 076 446.62; позиции A — 20 лотов, B — 500 лотов; при close A = 260.00 и B = 0.0300 стоимость портфеля `1278446.62`; комиссии всего 1980.42, сборы 396.16.

- **Готово, когда:** тест зелёный; таблица перенесена в `testdata/reference-portfolio.md`; в `invariants.md` (задача 54) INV-6 ссылается на тест.

### Задача 18: DSL: проверка типов и чтения будущего

- **Размер:** M. **Волна:** 3. **Зависит от:** 9. **Связано:** ФТ-12, ФТ-14, INV-1, INV-9, `dsl.md` («Типы», «Данные», «Диагностики»).

**Files:** Create: `src/core/include/core/dsl/checker.hpp`, `src/core/dsl/checker.cpp`, `tests/dsl/checker_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core::dsl {
struct ResolvedParam { std::string name; double value; std::optional<double> min, max, step; bool integer; };
struct CheckResult { Level level; std::vector<Diagnostic> diagnostics; std::vector<ResolvedParam> params; };
CheckResult check(const Program&);                    // E-TYPE, E-BEC, E-LA01, E-LA02, W-LA01
Level overallLevel(const std::vector<Diagnostic>&);   // худший; без диагностик — Ok
}
```

**Тесты:**
- `Checker.ReferenceIsOk`: эталонная стратегия → `Level::Ok`, 6 параметров, `fast.integer == true`.
- `Checker.NegativeOffsetIsLookAhead`: `close[-1]` → `E-LA01`, уровень `Error`.
- `Checker.ParamOffsetWithNegativeRange`: `param k = 1 range -2..3 step 1` и `close[k]` → `E-LA02`.
- `Checker.AbsolutePriceLevel`: `close > 271.35` → `W-LA01`; `rsi(close, 14) > 70` → без `W-LA01`.
- `Checker.NoNewsAccess` (INV-9): `when news > 0` → `E-TYPE` «неизвестное имя `news`».
- `Checker.EmptyBecause`: `because ""` → `E-BEC`.
- `Checker.BuyAllIsError`: `buy all` → `E-TYPE`.
- `Checker.NonIntegerPeriod`: `sma(close, 2.5)` → `E-TYPE`.

### Задача 19: DSL: линтер магических констант

- **Размер:** S. **Волна:** 3. **Зависит от:** 9. **Связано:** ФТ-13, `dsl.md` («Линтер»).

**Files:** Create: `src/core/include/core/dsl/linter.hpp`, `src/core/dsl/linter.cpp`, `tests/dsl/linter_test.cpp`.

**Interfaces (Produces):** `std::vector<Diagnostic> lint(const Program&, std::string_view source);` — диагностики `L001` (уровень `Warning`) с исправлением из двух правок: вставка `param <имя> = <литерал>\n` в начало первой строки первого правила и замена литерала именем.

**Тесты:**
- `Linter.ReferenceHasNoWarnings`.
- `Linter.FunctionArgument`: `sma(close, 20)` → `L001`, имя `sma_n`, исправление заменяет `20` на `sma_n`.
- `Linter.ComparedWithCall`: `rsi(close, rsi_n) > 70` → имя `rsi_level`.
- `Linter.FallbackNamesAndSuffix`: два литерала вне функций → `p1`, `p2`; если `p1` занято параметром — `p1_2`.
- `Linter.AllowsZeroOneHundred`: `0`, `1`, `100` — без диагностик.

### Задача 20: DSL: интерпретатор правил

- **Размер:** M. **Волна:** 4. **Зависит от:** 10, 11, 18. **Связано:** ФТ-12, ФТ-19, INV-1, INV-4, `dsl.md` («Как исполняется», «Действия», «Причина»).

**Files:** Create: `src/core/include/core/dsl/interpreter.hpp`, `src/core/dsl/interpreter.cpp`, `tests/dsl/interpreter_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core::dsl {
using ParamValues = std::map<std::string, double>;        // переопределения; остальное — значения по умолчанию
struct StateView { std::int64_t positionLots; std::optional<double> entryPrice; double cash, equity; std::optional<std::int64_t> barsInPosition; };
struct Intent { int instrument; std::string ruleName, because; bool cancelAll; OrderSpec order; };
class StrategyInstance {
 public:
  StrategyInstance(const Program&, const std::vector<ResolvedParam>&, const ParamValues&, std::size_t instrumentCount);  // значение вне диапазона — std::invalid_argument
  void onBar(int instrument, const StepBar& bar);                         // обновить ряды и индикаторы бумаги
  std::vector<Intent> evaluate(int instrument, const StepBar& bar, std::int64_t lotSize, const Decimal& priceStep, const StateView&);
};
Decimal toDecimalPrice(double value, const Decimal& priceStep);   // to_chars(fixed, 9) → Decimal::parse → roundToStep(HALF_UP)
}
```

Правила: см. `dsl.md`; размеры — по таблице «Действия», в `double`, затем `floor`; цена — `toDecimalPrice`; `because` — подстановка числа: `to_chars(fixed, 9)` → `Decimal` → `round(2, HALF_UP)` → без лишних нулей → точка на запятую; `na` → «н/д». Книга «одна активная заявка на правило» и снятие продаж при нулевой позиции — не здесь, а в задаче 21.

**Тесты:**
- `Interpreter.CrossoverFiresOnce`: close 10, 9, 8, 9, 11, 12 и правило `when crossover(sma(close, 2), sma(close, 3)) then buy 1 lots` → намерение покупки только на баре с индексом 4 (sma₂ = 10 > sma₃ = 9.333…, на баре 3 было 8.5 ≤ 8.667).
- `Interpreter.PercentCashSizing`: cash 1 000 000, close 271.35, лот 10, `buy 95 % cash` → 350 лотов.
- `Interpreter.BecauseFormatting`: `because "RSI = {rsi(close, 3)}"` на баре с rsi 66.6666666667 → `"RSI = 66,67"`; `{na}` → `"н/д"`.
- `Interpreter.StopPriceRounding`: `entry_price * 0.95` при `entry_price = 271.54`, шаг 0.01 → `257.96` (257.963 → HALF_UP).
- `Interpreter.ParamOverrideOutOfRange`: `fast = 60` при диапазоне 5..50 → `std::invalid_argument`.
- `Interpreter.IndicatorsUpdateDespiteShortCircuit`: `when false and sma(close, 3) > 0` 3 бара, затем `when sma(close, 3) > 0` на 4-м — значение равно sma последних трёх, а не `na`.

### Задача 21: Прогон стратегии и проверки во время исполнения

- **Размер:** M. **Волна:** 5. **Зависит от:** 15, 20. **Связано:** ФТ-1, ФТ-8, ФТ-14, НФТ-2, INV-3, INV-4, `dsl.md` («Чтение будущего»).

**Files:** Create: `src/core/include/core/run/backtest.hpp`, `src/core/run/{backtest,runtime_checks,digest}.cpp`, `tests/run/{backtest_test,determinism_test}.cpp`. Delete: `src/core/deterministic_run.cpp`, `src/core/include/core/deterministic_run.hpp`, `tests/determinism_test.cpp` и их строки в `src/core/CMakeLists.txt`, `tests/CMakeLists.txt` (заглушка каркаса заменяется настоящим тестом детерминизма).

**Interfaces (Produces):**

```cpp
namespace core {
struct Finding { std::string code; dsl::Level level; std::string message; std::int64_t step; };
enum class RunStatus { Completed, BankruptStop, Invalid };
struct RunOutput { RunStatus status; dsl::Level level; std::int64_t lastStep; std::vector<Fill> fills; std::vector<Order> orders;
                   std::vector<EquityPoint> equity; std::vector<RoundTrip> roundTrips; std::vector<Finding> findings;
                   std::vector<JournalEntry> journal; std::uint64_t digest; Decimal finalEquity; std::int64_t rejections, partialFills; };
using Progress = std::function<void(std::int64_t done, std::int64_t total)>;
RunOutput runBacktest(const SessionSpec&, std::shared_ptr<const Timeline>, const dsl::Program&,
                      const std::vector<dsl::ResolvedParam>&, const dsl::ParamValues&, dsl::Level staticLevel, const Progress&);
std::uint64_t digestOf(const RunOutput&);   // FNV-1a 64
}
```

Алгоритм: `SessionEngine`; на каждом шаге k после обработки — `onBar` и `evaluate` для бумаг с баром на k (в порядке бумаг); намерения превращаются в записи журнала (`seq` подряд, `step = k`) и применяются через `SessionEngine::apply` — тот же путь, что у журнала человека (INV-3). Книга правил: (правило, бумага) → id активной заявки; новая заявка правила снимает прежнюю (`CancelCmd{id, RuleReplaced}`), совпадающая — пропускается. После шага: по бумагам с нулевой позицией — `CancelCmd{id, PositionClosed}` для активных продаж стратегии. Прогресс — каждые 1000 шагов и в конце.

Проверки (`dsl.md`): нарушение целостности (`IntegrityViolation`, бросает движок при попытке прочитать бар позже текущего или исполнить раньше следующего бара) → `Invalid`, находка `E-RT01`; `W-RT01` угаданные гэпы (порог 2 %, ≥ 5, ≥ 80 %); `W-RT02` доля прибыльных пар > 90 % при ≥ 30 парах. `level = max(staticLevel, находки)`.

Отпечаток: FNV-1a 64 по байтам строки, где через `\n` идут: для каждой сделки `orderId|step|instrument|side|lots|price|value|commission|fee` (`Decimal::toString()`), затем для каждой точки `step|equity`, затем статус.

**Тесты:**
- `Backtest.SimpleRulesOnFixture`: бумага A из `fixture1()`, правила `rule "b" when close > close[1] and position == 0 then buy 10 lots because "рост"` и `rule "s" when close < close[1] and position > 0 then sell all because "падение"` → три сделки: покупка на шаге 2 по `101.07` (base 101, `frac = 0.0001`, `raw = 101.0606`), продажа на шаге 5 по `103.93` (`raw = 103.9376`), покупка на шаге 8 по `102.07` (`raw = 102.0612`); `because` — «рост», «падение», «рост».
- `Determinism.SameDigestTwice` (INV-4): два прогона → равные `digest`; прогон с другим параметром → другой.
- `Backtest.SameEngineAsHuman` (INV-3): `replaySession` с `output.journal` → те же `fills` побайтно.
- `Backtest.StopCancelledWhenFlat`: стоп правила «стоп» снимается с `PositionClosed` после выхода по «перекупленности».
- `RuntimeChecks.GapLuckWarning`: синтетические бары с 6 гэпами вверх ≥ 2 %, стратегия покупает за бар до каждого → `W-RT01`.
- `RuntimeChecks.IntegrityViolationInvalidates`: тестовый движок, бросающий `IntegrityViolation`, → `Invalid`, `E-RT01`.

### Задача 22: Метрики отчёта

- **Размер:** M. **Волна:** 3. **Зависит от:** 8. **Связано:** ФТ-17, НФТ-4, INV-6, `decisions.md` («Действующие решения v1»).

**Files:** Create: `src/core/include/core/report/metrics.hpp`, `src/core/report/metrics.cpp`, `tests/report/metrics_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
struct MetricsInput { Decimal initialCash; std::vector<EquityPoint> equity; std::vector<std::int32_t> tradingDayOfStep;
                      std::vector<Fill> fills; std::vector<RoundTrip> roundTrips; std::int64_t rejections, partialFills;
                      std::vector<std::vector<Decimal>> positionValuesByStep;   // [шаг][бумага]
                      std::optional<std::pair<Decimal, Decimal>> benchmark; };  // (open первого бара, close последнего)
struct Metrics { double totalReturn, grossReturn; std::optional<double> cagr; double maxDrawdown; std::int64_t maxDrawdownSteps;
                 std::optional<double> volatility, sharpe, sortino; double turnover; std::int64_t fills, roundTrips;
                 std::optional<double> winRate; std::int64_t rejections, partialFills; double hhiAvg, maxPositionShare;
                 std::optional<double> benchmarkReturn; std::int32_t tradingDays; };
struct CostTotals { Decimal commission, fee, spread, slippage; };
struct Report { Metrics metrics; CostTotals costs; std::vector<EquityPoint> equity; Decimal finalEquity; };
Report computeReport(const MetricsInput&);
}
```

Формулы (предложение плана, безрисковая ставка 0): E₀ — капитал; E_d — стоимость на последнем шаге торгового дня d; r_d = E_d / E_{d−1} − 1; D — число дней.
- `totalReturn = E_T / E₀ − 1`; `grossReturn = totalReturn + (Σ комиссий + Σ сборов) / E₀`.
- `cagr = (E_T / E₀)^(252 / D) − 1`, при D = 0 — нет.
- `volatility = stdev_выборочное(r) · √252`, при D < 2 — нет; `sharpe = mean(r) / stdev_выборочное(r) · √252`, при stdev = 0 — нет; `sortino = mean(r) / √(mean(min(r, 0)²)) · √252`, при знаменателе 0 — нет.
- `maxDrawdown = max_t (1 − E_t / max_{u≤t} E_u)` по шагам; `maxDrawdownSteps` — наибольшее число подряд идущих шагов ниже предыдущего максимума.
- `turnover = Σ value сделок / mean(E_d)`; `winRate` — доля пар с `netPnl > 0`, при 0 пар — нет.
- `hhiAvg` — среднее по шагам с позициями Σ w_i², w_i — доля стоимости позиции в сумме стоимостей позиций; `maxPositionShare` — максимум по шагам стоимости крупнейшей позиции / E_t.
- `benchmarkReturn = close / open − 1` бенчмарка.
- Деньги — `Decimal`, переводятся в `double` только здесь (`toDouble()`).

**Тесты** (дневной ряд стоимости 1 000 000 → 1 010 000, 1 005 000, 1 020 000, 990 000, 1 030 000; по шагу на день; допуск 1e-9):
- `totalReturn == 0.03`, `cagr == 3.4360468599`, `volatility == 0.4088278812`, `sharpe == 3.8176079043`, `sortino == 7.3710457334`, `maxDrawdown == 0.0294117647`, `maxDrawdownSteps == 1`.
- `Metrics.OneDayHasNoVolatility`: один день → `volatility`, `sharpe`, `sortino` пустые.
- `Metrics.CostsSummed`: сделки из строк 1–3 таблицы задачи 16 → комиссии `239.79`, сборы `47.97`.

### Задача 23: Воркер: обработчики RPC (каркас)

- **Размер:** S. **Волна:** 3. **Зависит от:** 1, 3, 7. **Связано:** ADR-0007.

**Files:** Modify: `src/worker/worker_service.{hpp,cpp}` (все RPC из контракта вызывают обработчики), `src/worker/main.cpp` (адрес из `WORKER_ADDRESS`, по умолчанию `0.0.0.0:50051`; бары — ClickHouse-адаптер задачи 34, календарь — пустой `InMemoryCalendarSource` до задачи 62). Create: `src/worker/handlers.hpp`, `src/worker/handlers/{check_strategy,replay_session,get_bars,run_backtest,walk_forward,analyze_divergences}.cpp` (каждый возвращает `UNIMPLEMENTED`), `tests/worker/handlers_scaffold_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace worker {
struct Context { core::BarSource& bars; core::CalendarSource& calendar; };
grpc::Status handleCheckStrategy(Context&, const pb::CheckStrategyRequest&, pb::CheckStrategyResponse*);
grpc::Status handleReplaySession(Context&, const pb::ReplaySessionRequest&, pb::ReplaySessionResponse*);
grpc::Status handleGetBars(Context&, const pb::GetBarsRequest&, pb::GetBarsResponse*);
grpc::Status handleRunBacktest(Context&, const pb::RunBacktestRequest&, grpc::ServerWriterInterface<pb::RunBacktestUpdate>*);
grpc::Status handleRunWalkForward(Context&, const pb::WalkForwardRequest&, grpc::ServerWriterInterface<pb::WalkForwardUpdate>*);
grpc::Status handleAnalyzeDivergences(Context&, const pb::DivergenceRequest&, pb::DivergenceResponse*);
}  // pb = pac::simulation::v1
```

- **Тесты:** `HandlersScaffold.AllRpcsReachable` — клиент в процессе вызывает каждый RPC, получает `UNIMPLEMENTED`; `Ping` — версию ядра.
- **Готово, когда:** каждая следующая задача воркера меняет только свой `handlers/<имя>.cpp` и свои `convert/*`.

### Задача 24: Воркер: CheckStrategy

- **Размер:** S. **Волна:** 4. **Зависит от:** 18, 19, 23. **Связано:** ФТ-12, ФТ-13, ФТ-14.

**Files:** Modify: `src/worker/handlers/check_strategy.cpp`. Create: `src/worker/convert/diagnostics.{hpp,cpp}`, `tests/worker/check_strategy_test.cpp`.

Ответ: `parse` → при ошибке только её диагностика; иначе `check` + `lint`, уровень — `overallLevel` без учёта `L001` (линтер на уровень не влияет, ФТ-13), параметры — из `check`.

- **Тесты:** эталонная стратегия → `OK`, 6 параметров; `close[-1]` → `ERROR`, `E-LA01`; литерал 20 → `OK` и диагностика `L001` с `fix` из двух правок.

### Задача 25: Воркер: ReplaySession и GetBars

- **Размер:** M. **Волна:** 5. **Зависит от:** 15, 22, 23. **Связано:** ФТ-6, ФТ-11, ФТ-17, INV-1, INV-8.

**Files:** Modify: `src/worker/handlers/{replay_session,get_bars}.cpp`. Create: `src/worker/convert/{market,state,report}.{hpp,cpp}`, `tests/worker/{replay_session_test,get_bars_test}.cpp`.

**Interfaces (Produces, используются задачами 28, 29, 59):**

```cpp
namespace worker {
core::SessionSpec toSessionSpec(const pb::MarketSpec&);
std::shared_ptr<const core::Timeline> loadTimeline(Context&, const pb::MarketSpec&);   // SnapshotNotFound, SecurityNotFound → FAILED_PRECONDITION
std::optional<std::pair<core::Decimal, core::Decimal>> loadBenchmark(Context&, const pb::MarketSpec&);  // по D1; нет бенчмарка — nullopt
core::JournalEntry fromProto(const pb::JournalEntry&, const core::SessionSpec&);
void toProto(const core::StepBar&, const core::Timeline&, pb::Bar*);   // также Order, Fill, PortfolioSnapshot, Report, Finding
core::MetricsInput metricsInput(const core::SessionEngine&, const core::Timeline&, std::optional<std::pair<core::Decimal, core::Decimal>> benchmark);
}
```

Поведение: `ReplaySession` — `replaySession` до `up_to_step` (больше `total_steps − 1` — `INVALID_ARGUMENT`); события — для шагов (`events_from_step`; `last_step`]; `history` — все бары шагов 0…`last_step`; `report` — при `include_report`. `GetBars` — бары шагов [`from_step`; `to_step`]. Ключ бумаги в proto (`instrument_key`) ↔ индекс в `MarketSpec.instruments`.

- **Тесты** (воркер в процессе, `Context` из `core::testing::fixture1()`): `ReplaySession.UpToStepNoFuture` (INV-1: `history` и `events` без шагов > 3); `ReplaySession.CommandResultsPerEntry`; `ReplaySession.ReportOnRequest` (`report.final_equity` = стоимость на `last_step`); `GetBars.Range`.

### Задача 26: Стресс-сценарий

- **Размер:** S. **Волна:** 3. **Зависит от:** 7. **Связано:** ФТ-23, `decisions.md` («Walk-forward, стресс…»).

**Files:** Create: `src/core/include/core/analysis/stress.hpp`, `src/core/analysis/stress.cpp`, `tests/analysis/stress_test.cpp`.

**Interfaces (Produces):** `struct StressScenario { std::int64_t startStep; Decimal gapPercent, volMultiplier; std::int32_t volBars; Decimal volumeShare; };` `Timeline applyStress(const Timeline&, const StressScenario&);`

Порядок и формулы — `decisions.md`; уточнения плана: каждая операция `Decimal` — 9 знаков HALF_UP; цены бара округляются до шага HALF_UP сразу, рекуррентность использует округлённый c′; множитель после окна f = c′/c — 9 знаков HALF_UP; объём — `floor(V · q)` лотов. Сценарий применяется к каждой бумаге по её барам на шагах ≥ `startStep`.

- **Тест** `Stress.WorkedExample` (одна бумага, шаг 0.01; бары O/H/L/C/V: 100/101/99/100/1000, 100/103/99/102/1000, 102/104/101/103/1000, 103/103/100/101/1000, 101/102/100/102/1000; t0 = 2, X = 10, k = 3, N = 2, q = 0.2) → бары 2…4: `71.40/76.80/68.70/74.10/200`, `74.10/74.10/67.63/69.78/200`, `69.78/70.47/69.09/70.47/1000`; бары 0–1 не меняются; `f = 0.767656766`.

### Задача 27: Наивный против честного: цепочка факторов и флаги

- **Размер:** S. **Волна:** 6. **Зависит от:** 21, 22. **Связано:** ФТ-24, INV-2 (исключение), INV-3.

**Files:** Create: `src/core/include/core/analysis/cost_breakdown.hpp`, `src/core/analysis/cost_breakdown.cpp`, `tests/analysis/cost_breakdown_test.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
enum class CostFactor { Naive, Delay, Fees, Spread, Slippage, Liquidity };
enum class CostFlag { CostsOverHalfProfit, SignChange, SharpeOver3 };
struct CostBreakdownStep { CostFactor factor; Decimal netResult; double netReturn; };
struct CostBreakdown { std::vector<CostBreakdownStep> steps; std::vector<CostFlag> flags; };
CostBreakdown costBreakdown(const SessionSpec& honest, std::shared_ptr<const Timeline>, const dsl::Program&,
                            const std::vector<dsl::ResolvedParam>&, const dsl::ParamValues&, std::optional<double> honestSharpe);
}
```

Шесть прогонов `runBacktest` с одной стратегией: `Naive` (`naive = true`, `CostConfig::zero()`), `Delay` (`naive = false`, нулевые издержки, без лимита), `Fees` (+ комиссия и сбор), `Spread` (+ спред), `Slippage` (+ κ), `Liquidity` (+ лимит) = честный. `netResult = finalEquity − initialCash`. Флаги — формулы `decisions.md`; `SharpeOver3` — по `honestSharpe`.

- **Тесты:** `CostBreakdown.SixStepsInOrder`; `CostBreakdown.LastEqualsHonestRun` (`netResult` шага `Liquidity` = результат обычного прогона); `CostBreakdown.Flags`: R_наивн = 1000, R_честн = 400 → `CostsOverHalfProfit`; R_наивн = 1000, R_честн = −10 → и `SignChange`; Sharpe 3.2 → `SharpeOver3`.

### Задача 28: Walk-forward (ядро и RPC)

- **Размер:** M. **Волна:** 6. **Зависит от:** 21, 22, 25. **Связано:** ФТ-22, ФТ-13, НФТ-2.

**Files:** Create: `src/core/include/core/analysis/walk_forward.hpp`, `src/core/analysis/walk_forward.cpp`, `tests/analysis/walk_forward_test.cpp`, `tests/worker/walk_forward_rpc_test.cpp`. Modify: `src/worker/handlers/walk_forward.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
struct WalkForwardConfig { std::int32_t fitDays = 250, testDays = 63, shiftDays = 63, maxGrid = 200; };
struct WalkForwardSegment { std::int32_t index; std::int32_t fitFromDay, fitToDay, testFromDay, testToDay;
                            dsl::ParamValues chosen; double fitNetReturn; RunOutput test; Report testReport; };
struct WalkForwardResult { std::vector<WalkForwardSegment> segments; double chainedReturn; };
std::vector<dsl::ParamValues> paramGrid(const std::vector<dsl::ResolvedParam>&, std::int32_t maxGrid);   // больше — std::invalid_argument
WalkForwardResult walkForward(const SessionSpec&, std::shared_ptr<const Timeline>, const dsl::Program&,
                              const std::vector<dsl::ResolvedParam>&, const WalkForwardConfig&, const Progress&);
}
```

Правила — `decisions.md`; сетка — декартово произведение в порядке объявления, последний параметр меняется быстрее всех; параметры без диапазона — по умолчанию; при равной доходности — лексикографически меньший набор. Окна — по торговым дням шкалы (`Timeline::slice`). RPC: даты окон — московские даты дней шкалы; прогресс — по сумме шагов всех прогонов.

- **Тесты:** `ParamGrid.Order`: `a ∈ {1,2}`, `b ∈ {10,20}` → `(1,10) (1,20) (2,10) (2,20)`; `ParamGrid.TooLarge`; `WalkForward.Segments`: шкала 400 торговых дней → 2 отрезка: подбор 1–250 / проверка 251–313 и подбор 64–313 / проверка 314–376 (третий, с проверкой 377–439, не помещается); `WalkForward.TieBreak`; `WalkForward.ChainedReturn`: проверочные доходности 0.1 и −0.05 → 0.045.

### Задача 29: Разбор расхождений (ядро и RPC)

- **Размер:** M. **Волна:** 6. **Зависит от:** 21, 25. **Связано:** ФТ-18, ФТ-19, ФТ-20, INV-3, INV-9, `decisions.md` («Разбор расхождений»).

**Files:** Create: `src/core/include/core/analysis/divergence.hpp`, `src/core/analysis/divergence.cpp`, `tests/analysis/divergence_test.cpp`, `tests/worker/divergence_rpc_test.cpp`. Modify: `src/worker/handlers/analyze_divergences.cpp`.

**Interfaces (Produces):**

```cpp
namespace core {
enum class DivergenceType { Excess, Missed, Size, Timing };
struct Divergence { std::string algorithmId; int instrument; DivergenceType type; std::int64_t humanStep, algoStep;
                    std::int64_t humanLots, algoLots, horizonStep; Decimal cost; double costPercent; std::string reason; };
struct MissedProfitableTrade { int instrument; std::int64_t entryStep, exitStep, lots; Decimal netPnl; std::vector<std::string> algorithmIds; };
struct ConsensusItem { int instrument; std::int64_t step; Side side; bool humanAction; std::int32_t agreeing, total; Decimal medianCost; };
struct AlgorithmInput { std::string id; dsl::Program program; std::vector<dsl::ResolvedParam> params; dsl::ParamValues values; };
struct DivergenceResult { std::vector<Divergence> divergences; std::vector<MissedProfitableTrade> missed; std::vector<ConsensusItem> consensus; std::vector<RunOutput> independent; };
DivergenceResult analyzeDivergences(const SessionSpec&, std::shared_ptr<const Timeline>, std::span<const JournalEntry> human,
                                    std::int64_t lastStep, const std::vector<AlgorithmInput>&);
}
```

Алгоритм — `decisions.md` дословно: действие — подача рыночной или лимитной заявки; алгоритм вычисляется на каждом шаге с `StateView` человека; W = 3; порог размера 20 %; горизонт e; V по исполнениям до e включительно; V алгоритма — копия `SessionEngine` человека на шаге t, в которой активные заявки человека сняты, применены заявки алгоритма, затем `advance()` до e; цена = V_алг − V_чел (копейки HALF_UP); `costPercent` — к стоимости портфеля человека на t; медиана для консенсуса; независимые портфели — `runBacktest` каждого алгоритма. Причина «лишнего действия» — «алгоритм здесь не действовал бы».

**Тесты** (одна бумага, лот 1, шаг 0.01, `CostConfig::zero()`, без лимита ликвидности; close по шагам 100, 100, 110, 110, 105, 105; open шага = close предыдущего, open шага 0 = 100):
- `Divergence.Missed`: алгоритм покупает 10 лотов на шаге 1, человек ничего не делает, других действий нет → горизонт — последний шаг 5; исполнение по open шага 2 = 100 → V_алг = 10 · (105 − 100) = 50, цена ошибки `50.00`, тип `Missed`.
- `Divergence.ExcessWithProfit`: человек покупает 10 на шаге 1 и продаёт на шаге 3, алгоритм молчит → два `Excess`: покупка — горизонт 3, V_чел = 10 · (110 − 100) = 100, цена `−100.00`; продажа — горизонт 5, исполнение по 110, V_чел = −10 · (105 − 110) = 50, цена `−50.00`. В `missed` — сделка с шагами исполнения 2 → 4, `netPnl == 100.00`.
- `Divergence.TimingWithinWindow`: человек покупает на шаге 1, алгоритм — на шаге 3 → `Timing`, `humanStep = 1`, `algoStep = 3`.
- `Divergence.SizeOver20Percent`: 10 против 13 лотов на одном шаге → `Size`; 10 против 11 → совпадение.
- `Divergence.OppositeSameStep`: человек покупает, алгоритм продаёт на одном шаге → одно `Excess`, `Missed` нет.
- `Divergence.Consensus`: 3 алгоритма, двое покупают вместе с человеком → `agreeing = 2`, `total = 3`.
- `Divergence.ProtectiveOrdersIgnored`: стоп человека не создаёт расхождения.

### Задача 34: Бары и чтение ClickHouse (уже в работе, task-list #10)

- **Репозиторий:** core. **Волна:** 0. **Зависит от:** 5, DI. **Связано:** ФТ-3, ФТ-4, ФТ-5, INV-1, INV-5, INV-10.
- Ветка `5-bar-source`. План опирается на её интерфейс: `src/core/include/core/market/{bar,bar_source,in_memory_bar_source,bar_cursor}.hpp` — `core::Bar` (`index`, `tsOpenMs`, `availableAtMs`, OHLC `Decimal`, `volume` в штуках, `value`), `core::Security`, `core::BarRequest{snapshotId, secid, intervalSec, fromMs, toMs}`, `core::BarSource{load, security}` с исключениями `SnapshotNotFound`, `SecurityNotFound`, `core::InMemoryBarSource`, `core::BarCursor`; ClickHouse-адаптер на libcurl в `src/worker/clickhouse/` (переменные окружения воркера `CLICKHOUSE_URL`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`); зависимость `curl` в `vcpkg.json`, Dockerfile и CI.
- Читает только `snapshots_ready`, `securities`, `candles`, `candles_from_trades` (INV-5: снапшот не меняется; INV-10: только `SELECT`).
- **Готово, когда:** влито в `main`. Чего в ветке нет из нужного плану — делает задача 62.

### Задача 62: ClickHouse: торговый календарь и свечи из сделок в воркере

- **Размер:** S. **Волна:** 3. **Зависит от:** 7, 23, 34. **Связано:** ФТ-3, ФТ-5.

**Files:** Create: `src/worker/clickhouse/clickhouse_calendar_source.{hpp,cpp}`, `src/worker/clickhouse/cached_bar_source.{hpp,cpp}`, `tests/worker/clickhouse_calendar_source_test.cpp`. Modify: `src/worker/main.cpp` (контекст воркера получает календарь и кэш), адаптер из задачи 34 — только если в нём нет пункта 2 ниже.

1. `ClickHouseCalendarSource : core::CalendarSource` — `SELECT toString(date), is_trading FROM trading_calendar WHERE snapshot_id = {sid:UUID} AND date BETWEEN {f:Date} AND {t:Date} ORDER BY date` (параметры — `param_*` HTTP-интерфейса, формат `TabSeparated`); нет снапшота в `snapshots_ready` → `SnapshotNotFound`.
2. Свечи из сделок: если интервала шага нет в `snapshots.intervals_sec`, а в `data_kinds` есть `trades`, адаптер читает те же столбцы из `candles_from_trades(snapshot_id = …, interval_sec = …)`.
3. `CachedBarSource(core::BarSource& inner, std::size_t capacity = 64)` — LRU по `BarRequest` и по `(snapshotId, secid)` для `security`; часы плеера дёргают воркер раз в 100–1000 мс, без кэша каждый шаг читал бы ClickHouse.

- **Тесты** (транспорт адаптера подменён записанными ответами): календарь разбирается из TSV; нет снапшота → `SnapshotNotFound`; второй одинаковый `load` через `CachedBarSource` не обращается к внутреннему источнику; при отсутствии интервала запрос идёт к `candles_from_trades`. Проверка на настоящем ClickHouse — в задаче 61.

### Задача 59: Воркер: RunBacktest (со стрессом и цепочкой издержек)

- **Размер:** S. **Волна:** 7. **Зависит от:** 24, 25, 26, 27. **Связано:** ФТ-1, ФТ-14, ФТ-17, ФТ-23, ФТ-24, НФТ-2, НФТ-5.

**Files:** Modify: `src/worker/handlers/run_backtest.cpp`. Create: `tests/worker/run_backtest_rpc_test.cpp`.

Поведение: `parse` + `check`; уровень `Error` → `INVALID_ARGUMENT` с кодами; параметры вне диапазона → `INVALID_ARGUMENT`; `start_step < 0` → `total_steps / 2`; `stress` с `vol_bars > 0` или `gap_percent > 0` или `volume_share > 0` → `applyStress`; `runBacktest` с прогрессом в поток; `report = computeReport(...)`; при `with_cost_breakdown` — `costBreakdown`; последнее сообщение потока — `result`.

- **Тесты:** прогресс приходит до результата; одинаковые запросы → одинаковый `digest`; стратегия с `close[-1]` → `INVALID_ARGUMENT`, в описании `E-LA01`; `with_cost_breakdown` → 6 шагов.

---

## Трек backend

Общее для задач трека: модуль `ru.ttsc.lab.<модуль>`; публичный API модуля — типы в корне пакета, реализация — `<модуль>.internal`, контроллеры и DTO (records) — `<модуль>.web`.

Граф модулей Spring Modulith (без циклов, иначе падает `ModularityTests`): `config`, `identity` — ни от кого не зависят; `worker` → `config`; `marketdata` → `config`; `workshop` → `worker`, `identity`, `config`; `sessions` → `worker`, `marketdata`, `identity`, `config`; `simulation` → `worker`, `workshop`, `marketdata`, `identity`, `config`; `analysis` → все остальные. События (`SessionFinished`, `RunCompleted`, `VersionPublished`) объявлены в модуле-источнике и слушаются в `analysis`. Обратных вызовов (например, `workshop` → `analysis`) нет.

Полей `double`/`float` в классах `ru.ttsc.lab` нет (`MoneyTypesArchTest`): параметры стратегий в DTO — `BigDecimal`; метрики — в сохранённом JSON (`JsonNode`) или в records пакета `analysis.metrics` (задача 44 исключает его из теста). Доступ к данным — Spring Data JDBC / `JdbcClient`. Тесты с PostgreSQL — Testcontainers (как `FlywayMigrationTest`); тест каждого эндпоинта вызывает `OpenApiContractAssert.assertMatches` (задача 4). Воркер в тестах — `@MockitoBean WorkerClient` с заранее собранными proto-ответами. Проверка — `./gradlew build` (PASS, включая `ModularityTests` и `MoneyTypesArchTest`), коммит по-русски. «Готово, когда» по умолчанию — CI `backend` зелёный и перечисленные тесты есть.

### Задача 12: Учётные записи (уже в работе, task-list #7)

- **Волна:** 0. **Связано:** UC-1, НФТ-6, `decisions.md` («Учётные записи»).
- Ветка `4-identity`: `V2__identity.sql`, `/api/auth/register`, `/api/auth/login`, `/api/me` (и выход), cookie-сессия, CSRF, `ProblemJsonHandlers`. Публичный API модуля, на который опираются задачи ниже: `ru.ttsc.lab.identity.CurrentUser` (id текущего пользователя, роли), `ru.ttsc.lab.identity.Role` (`USER`, `MODERATOR`).
- **Готово, когда:** влито; `openapi.yaml` (задача 2) описывает эндпоинты так, как они сделаны.

### Задача 33: worker: клиент воркера (отдельный модуль)

- **Размер:** S. **Волна:** 3. **Зависит от:** 4. **Связано:** ADR-0007, ADR-0008, INV-6.

**Files:** Create: `worker/package-info.java` (`@ApplicationModule`), `worker/WorkerClient.java`, `worker/Decimals.java`, `worker/MarketSpecs.java`, `worker/WorkerUnavailableException.java`, `worker/WorkerRejectedException.java`, `worker/DataUnavailableException.java`, `worker/internal/GrpcWorkerClient.java`, `worker/internal/WorkerChannelConfig.java`; тесты `worker/DecimalsTest.java`, `worker/internal/GrpcWorkerClientTest.java` (сервер `grpc-inprocess`).

Отдельный модуль нужен, чтобы `workshop`, `sessions` и `simulation` звали воркер без циклов (`simulation` сам зависит от `workshop`).

**Interfaces (Produces):**

```java
public interface WorkerClient {
  CheckStrategyResponse checkStrategy(String source);
  ReplaySessionResponse replaySession(ReplaySessionRequest request);
  GetBarsResponse getBars(GetBarsRequest request);
  RunResult runBacktest(RunBacktestRequest request, Consumer<RunProgress> onProgress);
  WalkForwardResult runWalkForward(WalkForwardRequest request, Consumer<RunProgress> onProgress);
  DivergenceResponse analyzeDivergences(DivergenceRequest request);
}
public final class Decimals {
  public static BigDecimal toBigDecimal(pac.simulation.v1.Decimal d);   // units + nano·10⁻⁹
  public static pac.simulation.v1.Decimal toProto(BigDecimal v);        // setScale(9, UNNECESSARY): лишние знаки — ArithmeticException
}
public final class MarketSpecs {
  public static CostConfig costs(LabProperties.Costs c);
  public static MarketSpec.Builder base(UUID snapshotId, Timeframe tf, LocalDate from, LocalDate to, List<Instrument> instruments, BigDecimal initialCash, CostConfig costs);
}
```

Коды gRPC → исключения: `UNAVAILABLE`, `DEADLINE_EXCEEDED` → `WorkerUnavailableException`; `INVALID_ARGUMENT` → `WorkerRejectedException(описание)`; `FAILED_PRECONDITION` → `DataUnavailableException`. Дедлайны — `lab.worker.unary-deadline` и `stream-deadline`.

**Тесты:** `DecimalsTest`: `"271.35"` ↔ `{271, 350000000}`; `"-0.000000001"` ↔ `{0, -1}`; `"-1.5"` ↔ `{-1, -500000000}`; `"0.0000000001"` → `ArithmeticException`; `{1, -1}` → `IllegalArgumentException`. `GrpcWorkerClientTest`: прогресс потока доходит до `onProgress` раньше результата; `INVALID_ARGUMENT` → `WorkerRejectedException`.

### Задача 17: marketdata: каталог, календарь, выбор периода

- **Размер:** M. **Волна:** 3. **Зависит от:** 4, DI. **Связано:** ФТ-1, ФТ-2, ФТ-3, ФТ-4, ФТ-5, UC-2, `decisions.md` («Запуск сессии и прогона»).

**Files:** Create: `marketdata/{MarketData,Timeframe,SnapshotInfo,InstrumentInfo,PeriodRequest,PeriodChoice,NoPeriodException,TooManyBarsException}.java`, `marketdata/internal/{ClickHouseMarketData,ClickHouseConfig,PeriodChooser}.java`, `marketdata/web/MarketDataController.java`; тесты `marketdata/internal/{PeriodChooserTest,ClickHouseMarketDataIT}.java`, `src/test/resources/marketdata/fixture.sql`.

**Interfaces (Produces):**

```java
public enum Timeframe { S1, S10, M1, M5, M10, M15, H1, D1; public int seconds() { … } }
public record SnapshotInfo(UUID id, Instant fetchedAt, String contentHash, Set<Integer> intervalsSec, boolean hasTrades, LocalDate from, LocalDate to) {}
public record InstrumentInfo(String ticker, String name, String sector, long lotSize, BigDecimal priceStep, LocalDate from, LocalDate to) {}
public enum StartType { RANDOM, DATE }
public record PeriodRequest(Timeframe timeframe, int durationDays, StartType start, Integer instrumentCount, LocalDate date, List<String> tickers, boolean manual) {}
public record PeriodChoice(UUID snapshotId, List<InstrumentInfo> instruments, LocalDate from, LocalDate to, boolean blind) {}
public interface MarketData {
  SnapshotInfo latestSnapshot();                      // последний по fetched_at среди snapshots_ready с securities и trading_calendar
  Optional<SnapshotInfo> snapshot(UUID id);
  List<Timeframe> availableTimeframes();              // интервалы снапшота; при наличии сделок — все
  List<InstrumentInfo> instruments(UUID snapshotId);  // from/to — покрытие свечами или сделками
  List<LocalDate> tradingDays(UUID snapshotId, LocalDate from, LocalDate to);
  PeriodChoice choosePeriod(PeriodRequest request);   // NoPeriodException, TooManyBarsException
}
```

Выбор периода (точно): RANDOM — пул = `lab.marketdata.blind-pool` ∩ бумаги снапшота с непустым `sector`; до 20 попыток: начало — равномерно среди торговых дней, от которых `durationDays` торговых дней помещаются в снапшот; бумаги, покрывающие весь отрезок, перемешиваются (`SplittableRandom` от `SecureRandom`), берутся первые `instrumentCount`; не хватило — следующая попытка; иначе `NoPeriodException`. DATE — начало = первый торговый день ≥ `date`, бумаги — `tickers` в заданном порядке, каждая должна покрывать отрезок. `blind = (start == RANDOM)`. Ручная сессия: оценка баров = `durationDays · (tf == D1 ? 1 : ceil(31500 / tf.seconds()))`; больше `lab.session.manual-max-bars` → `TooManyBarsException`. ClickHouse — отдельный `DataSource` (`clickhouse-jdbc`, настройки `lab.clickhouse`), только `SELECT` (INV-10, ADR-0004).

**Тесты:**
- `PeriodChooserTest` (календарь и покрытие в памяти): `randomCoversDuration`; `noPeriodWhenTooLong`; `tooManyBarsForManualM1` (250 дней × M1 = 131 250 баров → исключение); `dateStartUsesGivenTickersInOrder`; `blindPoolRequiresSector`.
- `ClickHouseMarketDataIT` (Testcontainers `clickhouse/clickhouse-server:25.8`, схема из `deploy/clickhouse/schema/*.sql`, данные `fixture.sql`): `latestSnapshotIgnoresFailed`; `timeframesFromIntervals` (60, 86400 → M1, D1; со сделками — все 8); `instrumentsWithCoverage`.
- Контракт: `GET /api/marketdata/timeframes`, `GET /api/marketdata/instruments`.

### Задача 30: sessions: создание, журнал, состояние, слепая маска

- **Размер:** M. **Волна:** 4. **Зависит от:** 17, 33. **Связано:** ФТ-1, ФТ-2, ФТ-11, UC-2, INV-5, INV-7, INV-8.

**Files:** Create: `src/main/resources/db/migration/V3__sessions.sql`, `sessions/{SessionQueries,SessionSnapshot,SessionSummary,InstrumentMeta}.java`, `sessions/internal/{SessionService,SessionRepository,JournalRepository,SessionViewMapper,BlindScaler,SessionLocks}.java`, `sessions/web/{SessionController,SessionDtos}.java`; тесты `sessions/internal/{BlindScalerTest,JournalImmutabilityTest}.java`, `sessions/web/{SessionApiTest,BlindContractTest}.java`.

`V3__sessions.sql`:

```sql
create table sessions.sessions (
  id uuid primary key, owner_id uuid not null,
  status text not null check (status in ('ACTIVE','FINISHED')),
  finish_reason text check (finish_reason in ('END','BANKRUPT','EARLY')),
  blind boolean not null, timeframe text not null, snapshot_id uuid not null,
  period_from date not null, period_to date not null,
  instruments jsonb not null,          -- [{key, ticker, name, sector, lotSize, priceStep, p0, v0}]
  costs jsonb not null, initial_cash numeric(38,9) not null,
  total_steps bigint not null, cursor bigint not null default 0,
  playing boolean not null default false, speed int not null default 1 check (speed in (1,5,10)),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), finished_at timestamptz);
create index sessions_owner_created on sessions.sessions(owner_id, created_at desc);
create table sessions.journal (
  session_id uuid not null references sessions.sessions(id), seq bigint not null, step bigint not null,
  seen_step bigint not null, client_order_id uuid not null, command jsonb not null,
  accepted boolean not null, reason text, created_at timestamptz not null default now(),
  primary key (session_id, seq), unique (session_id, client_order_id));
-- триггер: update и delete в sessions.journal → исключение «журнал неизменяем (INV-8)»
```

**Interfaces (Produces):**

```java
public record InstrumentMeta(String key, String ticker, String name, String sector, long lotSize, BigDecimal priceStep, BigDecimal p0, long v0) {}
public record SessionSnapshot(UUID id, UUID ownerId, String status, String finishReason, boolean blind, MarketSpec market,
                              List<JournalEntry> journal, long cursor, long totalSteps, List<InstrumentMeta> instruments,
                              LocalDate periodFrom, LocalDate periodTo, Instant createdAt, Instant finishedAt) {}
public record SessionSummary(UUID id, String status, String finishReason, boolean blind, String timeframe, Instant createdAt, List<InstrumentMeta> instruments) {}
public interface SessionQueries { Optional<SessionSnapshot> find(UUID id); List<SessionSummary> listByOwner(UUID ownerId); }
// internal, используют задачи 31, 32, 40:
class SessionLocks { SessionRow lockForUpdate(UUID sessionId); }                       // SELECT … FOR UPDATE
class SessionService { ReplaySessionResponse replay(SessionRow s, long upTo, long eventsFrom, boolean history, boolean report); }
class SessionViewMapper { SessionView toView(SessionRow s, ReplaySessionResponse r); StepEvent toStepEvent(SessionRow s, StepEvents e); }
class BlindScaler { String price(BigDecimal real, BigDecimal p0); BigDecimal unscale(BigDecimal shown, BigDecimal p0, BigDecimal priceStep); String volume(long lots, long v0); }
```

Создание: `choosePeriod(manual = true)` → `MarketSpec` (ключи A…E по порядку, издержки и капитал из `lab.*`, `benchmark_ticker = "IMOEX"`) → `replaySession(up_to 0)` даёт `total_steps`; `getBars(0, min(total − 1, 1000))` — первый бар каждой бумаги: `p0 = open`, `v0 = max(volume_lots, 1)`; нет бара — `NoPeriodException`. `GET` — `replaySession(up_to = cursor, include_history)` и маска. Чужая сессия — 404.

Маска слепого режима (INV-7, `decisions.md`, «Деньги и округление», п. 8): `label = "Бумага " + key`, только сектор; нет `ticker`, `name`, `priceStep`, `time`; цены — `price · 100 / p0`, 6 знаков HALF_UP, без лишних нулей; объём — `lots / v0`, 4 знака HALF_UP; средняя цена позиции и цены заявок — так же; суммы в рублях не меняются. Ошибки, уходящие клиенту, не содержат тикер и даты.

**Тесты:**
- `BlindScalerTest`: `price(271.35, 271.35) == "100"`; `price(284.9175, 271.35) == "105"`; `unscale(105, 271.35, 0.01) == 284.92`; `volume(150, 1000) == "0.15"`.
- `BlindContractTest` (INV-7): JSON ответа `GET /api/sessions/{id}` слепой сессии не содержит тикеров и названий бумаг сессии, строк вида `\d{4}-\d{2}-\d{2}` и полей `time`, `ticker`, `name`; `bars[0].open == "100"`.
- `SessionApiTest`: `createRandomSession` (201, `cursor == 0`, `blind == true`); `createDateSessionIsNotBlind` (тикеры видны); `noPeriod422`; `tooManyBars422`; `foreignSession404`; `getReplaysUpToCursor` (запрос к воркеру — `up_to_step == cursor`).
- `JournalImmutabilityTest` (INV-8): `update`/`delete` строки журнала через JDBC → исключение.

### Задача 31: sessions: плеер, часы, SSE

- **Размер:** M. **Волна:** 5. **Зависит от:** 30. **Связано:** ФТ-6, ФТ-11, НФТ-5, НФТ-6, ADR-0002, INV-1, INV-8, UC-3, UC-6.

**Files:** Create: `sessions/SessionEndReached.java` (событие: `UUID sessionId, String status`), `sessions/internal/{SessionClock,SseHub,PlayerService,StartupPause}.java`, `sessions/web/{PlayerController,SessionEventsController}.java`; тесты `sessions/internal/{SessionClockTest,SseHubTest}.java`, `sessions/web/PlayerApiTest.java`.

Поведение:
- `play(speed)`: `playing = true`, `speed`; тик каждые `1000 / speed` мс (ScheduledExecutorService на один поток). Тик в транзакции: `lockForUpdate`; не `ACTIVE` или не `playing` — тик снимается; `replay(up_to = cursor + 1, events_from = cursor)`; `cursor = last_step`; событие `step` в `SseHub`; статус ответа `FINISHED_END` или `BANKRUPT` → `playing = false`, событие `SessionEndReached` (обрабатывает задача 40).
- `pause` — `playing = false`, событие `state`. `step` — один тик при паузе; при игре — 409 `SESSION_PLAYING`.
- `SseHub`: `SseEmitter` без таймаута на подписчика; комментарий-heartbeat каждые 15 с; когда подписчиков сессии 0 дольше `lab.session.disconnect-pause-after` — пауза (ADR-0002).
- `StartupPause`: при старте приложения `playing = false` у всех сессий (ревью, п. 5).
- Тик и заявка (задача 32) берут одну блокировку строки сессии (ревью, п. 2).

**Тесты:**
- `PlayerApiTest`: `playAdvancesCursor` (×10, Awaitility: `cursor ≥ 3` за 2 с); `stepWhilePlaying409`; `stepAdvancesByOne`; `pauseStops`.
- `SseHubTest`: `stepEventBarsOnlyAtCursor` (INV-1: у всех баров события `step == cursor`); `pausesWhenNoSubscribers` (настройка 200 мс).
- `SessionClockTest`: `restartOpensPaused`; `concurrentTicksAndOrdersSerialize` — 20 тиков и 20 заявок из двух потоков: `cursor` не убывает, `step` записей журнала не убывает по `seq`, взаимной блокировки нет.

### Задача 32: sessions: заявки

- **Размер:** S. **Волна:** 5. **Зависит от:** 30. **Связано:** ФТ-7, ФТ-11, UC-4, UC-5, INV-2, INV-8, `decisions.md` («Заявки»).

**Files:** Create: `sessions/internal/OrderService.java`, `sessions/web/OrderController.java`; тест `sessions/web/OrderApiTest.java`.

Поведение: проверка формы (`lots ≥ 1`, цены по типу) → 422 `INVALID_PARAMS` с `field`; `lockForUpdate`; повтор `clientOrderId` — тот же ответ без новой записи (ревью, п. 1); сессия не `ACTIVE` → `accepted = false`, `SESSION_NOT_ACTIVE`; в слепой сессии цены переводятся `BlindScaler.unscale`; в неслепой — округляются до шага HALF_UP; запись журнала: `seq = max + 1`, `step = cursor` (INV-2: не раньше последнего показанного), `seen_step` из запроса; `replay(up_to = cursor)` с новой записью → `command_results[seq]` → строка журнала с `accepted`, `reason` → ответ `OrderPlacement` (заявки из `order_ids`, с маской). Отмена и замена — записи `cancel` / `replace` тем же путём.

**Тесты:** `journaledAtCursorNotSeenStep` (`seenStep = 2`, `cursor = 5` → `step = 5`); `duplicateClientOrderIdIsIdempotent`; `blindLimitPriceUnscaled` (показанная 105 при `p0 = 271.35` → воркер получает `284.92`); `rejectedOrderIsJournaled`; `cancelFilledOrderNotActive` (воркер вернул `ORDER_NOT_ACTIVE` → `accepted = false`); `replaceIsOneEntry`.

### Задача 40: sessions: завершение, раскрытие, данные для воспроизведения

- **Размер:** S. **Волна:** 6. **Зависит от:** 31. **Связано:** ФТ-2, ФТ-10, ФТ-11, ФТ-17, UC-7, UC-8, UC-11, INV-7.

**Files:** Create: `sessions/SessionFinished.java` (событие: `UUID sessionId, UUID ownerId, boolean blind, byte[] report, byte[] market`), `sessions/internal/FinishService.java`, `sessions/web/{FinishController,ReplayController}.java`; тест `sessions/web/FinishApiTest.java`.

Поведение: `SessionEndReached` → `finish(END | BANKRUPT)`; `POST /finish` → `finish(EARLY)` (отрезок — до `cursor`). `finish`: статус `FINISHED`, причина, `finished_at`, `playing = false`; `replay(up_to = cursor, include_report)`; событие `SessionFinished` с байтами `Report` и `MarketSpec`; SSE `finished` с `Reveal`. После завершения `GET` отдаёт данные без маски и с `reveal`. `GET /replay` — только для завершённой (иначе 409): `getBars(0, cursor)` + заявки и сделки из `replay`, без маски.

**Тесты:** `earlyFinishPublishesReport`; `endReachedFinishesWithEnd`; `bankruptReason`; `revealOnlyAfterFinish` (INV-7: до завершения `reveal` нет, после — тикеры и даты есть); `replayConflictBeforeFinish`.

### Задача 35: simulation: очередь фоновых заданий

- **Размер:** M. **Волна:** 3. **Зависит от:** 4. **Связано:** НФТ-5, UC-14, UC-24.

**Files:** Create: `src/main/resources/db/migration/V7__simulation_jobs.sql`, `simulation/{JobQueue,JobHandler,NonRetriableJobException}.java`, `simulation/internal/{JdbcJobQueue,JobRunner}.java`; тест `simulation/internal/JobRunnerTest.java`.

```sql
create table simulation.jobs (
  id uuid primary key, type text not null, payload jsonb not null,
  status text not null check (status in ('QUEUED','RUNNING','DONE','FAILED')),
  attempts int not null default 0, locked_until timestamptz, error text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index jobs_status_created on simulation.jobs(status, created_at);
```

```java
public interface JobQueue { UUID enqueue(String type, JsonNode payload); }
public interface JobHandler { String type(); void handle(UUID jobId, JsonNode payload) throws Exception; }   // бины из любых модулей
```

`JobRunner`: `lab.jobs.concurrency` потоков; опрос каждые `poll-interval`; захват — `UPDATE … WHERE id = (SELECT id FROM simulation.jobs WHERE status = 'QUEUED' OR (status = 'RUNNING' AND locked_until < now()) ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *` с `RUNNING`, `attempts + 1`, `locked_until = now() + lease`; продление аренды каждые `lease / 2`, пока задание выполняется; успех → `DONE`; исключение → `QUEUED` при `attempts < max-attempts`, иначе `FAILED` с текстом; `NonRetriableJobException` → сразу `FAILED`.

**Тесты:** `claimedOnce` (два раннера, одно задание → один вызов); `retriesThenFails`; `nonRetriableFailsImmediately`; `expiredLeaseRequeued` (ревью, п. 5).

### Задача 36: simulation: прогоны алгоритмов

- **Размер:** M. **Волна:** 6. **Зависит от:** 17, 33, 35, 39. **Связано:** ФТ-1, ФТ-8, ФТ-14, ФТ-23, ФТ-24, НФТ-2, НФТ-3, НФТ-5, UC-14, UC-15, UC-17, INV-4, INV-5.

**Files:** Create: `src/main/resources/db/migration/V8__simulation_runs.sql`, `simulation/{RunService,RunQueries,RunSummary,RunCompleted,RunPurpose}.java`, `simulation/internal/{RunJobHandler,RunRepository,RunSseHub,StressPresets}.java`, `simulation/web/{RunController,RunDtos}.java`; тест `simulation/web/RunApiTest.java`.

```sql
create table simulation.runs (
  id uuid primary key, owner_id uuid, version_id uuid not null, params jsonb not null,
  purpose text not null check (purpose in ('USER','RATING','WALK_FORWARD')), blind boolean not null,
  market bytea not null,                 -- MarketSpec (proto)
  stress jsonb, stress_pair_run_id uuid, repeat_of uuid, repeat_matches boolean,
  status text not null check (status in ('QUEUED','RUNNING','DONE','FAILED')),
  run_status text, level text, digest text, progress_done bigint not null default 0, progress_total bigint not null default 0,
  result bytea, error text, created_at timestamptz not null default now(), finished_at timestamptz);
create index runs_owner_created on simulation.runs(owner_id, created_at desc);
```

**Interfaces (Produces):**

```java
public enum RunPurpose { USER, RATING, WALK_FORWARD }
public record RunSpec(UUID ownerId, UUID versionId, Map<String, Double> params, RunPurpose purpose, MarketSpec market, boolean blind,
                      StressScenario stress, boolean withCostBreakdown, UUID repeatOf) {}
public interface RunService { UUID submit(RunSpec spec); }
public record RunSummary(UUID id, UUID ownerId, UUID versionId, RunPurpose purpose, boolean blind, String status, String runStatus,
                         String level, String digest, UUID repeatOf, Boolean repeatMatches, Instant createdAt, Instant finishedAt) {}
public interface RunQueries { Optional<RunSummary> find(UUID id); List<RunSummary> listByOwner(UUID ownerId); Optional<byte[]> result(UUID id); Optional<MarketSpec> market(UUID id); }
public record RunCompleted(UUID runId, UUID ownerId, RunPurpose purpose, UUID versionId, boolean blind, byte[] result, byte[] market) {}
```

Поведение `POST /api/runs`: версия видна пользователю (`StrategyVersions.find`, задача 39: своя или опубликованная и не удалённая; иначе 404); параметры — в пределах `ParamDecl` (иначе 422 `INVALID_PARAMS`, поле `params.<имя>`); период — `choosePeriod(manual = false)`; стресс: `PARAMETRIC` — два прогона: без стресса (возвращается) и со стрессом (`stressPairRunId`), значения по умолчанию X = 10, k = 3, N = 20, q = 0.2, `start_step = −1` — середина периода (обрабатывает задача 59); `PRESET` — период `FEB_2022` = 2021-12-01…2022-05-31, `MAR_2020` = 2020-01-01…2020-06-30, пара — прогон стратегии «купить и держать» на том же окне (текст генерируется: `rule "купить" when position == 0 then buy <floor(100 / N)> % cash because "купить и держать"`, N — число бумаг). Задание `RUN` → `runBacktest(with_cost_breakdown = purpose == USER)`; прогресс в БД не чаще раза в секунду и в SSE (`progress`); итог — `result`, `digest` (16 hex-символов), `run_status`, `level`, событие `RunCompleted`, SSE `completed`. `WorkerRejectedException` → `NonRetriableJobException`. `GET /replay` — `getBars` + сделки и заявки из `result`; баров больше 50 000 — 422 `TOO_LARGE`.

Значения параметров в `RunRequest` и `Run` — `BigDecimal` (в proto переводятся в `double` при сборке `StrategySource`).

**Тесты:** `submitQueuesJob`; `jobStoresResultAndPublishesEvent`; `paramsOutOfRange422`; `hiddenForeignVersion404`; `presetOverridesPeriod`; `parametricCreatesPair`; `invalidStrategyFailsWithoutRetry`; `progressEventsOverSse`.

### Задача 37: simulation: walk-forward

- **Размер:** S. **Волна:** 7. **Зависит от:** 36. **Связано:** ФТ-22, UC-16.

**Files:** Create: `src/main/resources/db/migration/V9__simulation_walk_forward.sql` (`simulation.walk_forwards(id uuid pk, owner_id uuid not null, version_id uuid not null, request jsonb not null, status text not null, progress_done bigint, progress_total bigint, result jsonb, error text, created_at, finished_at)`), `simulation/internal/WalkForwardJobHandler.java`, `simulation/web/WalkForwardController.java`; тест `simulation/web/WalkForwardApiTest.java`.

Поведение: `POST` — тикеры и даты из запроса (неслепой), `fit/test/shift/max-grid` из `lab.walk-forward`; задание `WALK_FORWARD` → `runWalkForward`; проверочный прогон каждого отрезка сохраняется строкой `runs` (`purpose = WALK_FORWARD`, `result`) и публикуется `RunCompleted` (отчёт строит задача 42); `testRunId` — её id.

**Тесты:** `segmentsMapped`; `gridTooLargeFails` (воркер → `INVALID_ARGUMENT` → `FAILED` с текстом); `testRunsHaveReports` (событие `RunCompleted` на каждый отрезок).

### Задача 60: simulation: повтор прогона (UC-18)

- **Размер:** S. **Волна:** 7. **Зависит от:** 36. **Связано:** НФТ-2, НФТ-3, INV-4, UC-18.

**Files:** Create: `simulation/internal/RepeatService.java`, `simulation/web/RepeatController.java`; тест `simulation/web/RepeatApiTest.java`.

Поведение: `POST /api/runs/{id}/repeat` — новый прогон с теми же `market`, версией, параметрами, стрессом, `repeat_of = id`; по `RunCompleted` повтора — `repeat_matches = (digest повтора == digest исходного)`; несовпадение — лог уровня ERROR «нарушение INV-4: прогон <id>».

**Тесты:** `sameDigestMatches`; `differentDigestFlagged`; `repeatOfForeignRun404`.

### Задача 38: workshop: стратегии, черновики, проверка

- **Размер:** S. **Волна:** 4. **Зависит от:** 33. **Связано:** ФТ-12, ФТ-13, ФТ-14, UC-12, UC-13.

**Files:** Create: `src/main/resources/db/migration/V4__workshop_strategies.sql`, `workshop/{Strategies,StrategyInfo}.java`, `workshop/internal/{StrategyService,StrategyRepository}.java`, `workshop/web/{StrategyController,StrategyDtos,CheckController}.java`; тест `workshop/web/StrategyApiTest.java`.

```sql
create table workshop.strategies (
  id uuid primary key, owner_id uuid,                -- null — платформа
  name text not null check (length(name) between 1 and 100),
  draft_source text not null default '', draft_updated_at timestamptz not null default now(),
  hidden boolean not null default false, deleted boolean not null default false,
  forked_from_version_id uuid, created_at timestamptz not null default now());
```

Поведение: список — свои неудалённые; черновик больше 64 КиБ — 422 `INVALID_PARAMS` (`source`); `POST /api/strategies/check` → `checkStrategy` → `CheckResult` (уровень, диагностики, параметры). Чужая стратегия — 404.

`ParamDecl` в `CheckResult` — с `BigDecimal`.

**Тесты:** `createAndList`; `draftTooLarge422`; `checkMapsDiagnosticsAndFixes`; `foreignStrategy404`.

### Задача 39: workshop: версии, публикация, форк, скрытие, эталонная стратегия

- **Размер:** M. **Волна:** 5. **Зависит от:** 38. **Связано:** ФТ-13, ФТ-15, ФТ-16, ФТ-18, UC-19, UC-20, UC-21, INV-5, `decisions.md` («Мастерская», «Мастерская: скрытие и удаление», «Разбор расхождений»).

**Files:** Create: `src/main/resources/db/migration/V5__workshop_versions.sql`, `workshop/{StrategyVersions,VersionInfo,ParamDeclView,VersionPublished}.java`, `workshop/internal/{VersionService,VersionRepository}.java`, `workshop/web/{VersionController,VersionDtos}.java`; тесты `workshop/web/VersionApiTest.java`, `workshop/internal/VersionImmutabilityTest.java`.

```sql
create table workshop.versions (
  id uuid primary key, strategy_id uuid not null references workshop.strategies(id), number int not null,
  source text not null, dsl_version int not null default 1, params jsonb not null, diagnostics jsonb not null,
  check_level text not null check (check_level in ('OK','WARNING','ERROR')),
  published boolean not null default false, published_at timestamptz, created_at timestamptz not null default now(),
  unique (strategy_id, number));
-- триггер (INV-5): update, меняющий source, params, diagnostics, number, strategy_id или published true → false, и любой delete → исключение «версия неизменяема (INV-5)»
-- эталон: стратегия 00000000-0000-0000-0000-000000000001 (owner_id null, «Эталон платформы»),
-- версия 00000000-0000-0000-0000-000000000002 (number 1, published, текст из dsl.md, params — 6 параметров, check_level OK)
```

**Interfaces (Produces):**

```java
public record ParamDeclView(String name, BigDecimal defaultValue, BigDecimal min, BigDecimal max, BigDecimal step, boolean integer) {}
public record VersionInfo(UUID id, UUID strategyId, String strategyName, UUID ownerId, int number, String source,
                          List<ParamDeclView> params, boolean published, boolean hidden, boolean deleted, String checkLevel, int lintWarnings) {}
public interface StrategyVersions {
  Optional<VersionInfo> find(UUID versionId);
  List<VersionInfo> publishedVisible();       // опубликованные, не скрытые, не удалённые
  VersionInfo reference();                    // эталон платформы
}
public record VersionPublished(UUID versionId) {}
```

Значения параметров — `BigDecimal`, а не `double` (`MoneyTypesArchTest`); в proto и JSON — числа.

Поведение: `POST /strategies/{id}/versions` — `checkStrategy(draft)`; уровень `ERROR` → 422 `DSL_ERRORS` (диагностики — в `errors` problem-ответа); иначе версия с `number = max + 1`. `publish` — владелец, однократно; событие `VersionPublished`. `GET /versions/{id}` — владельцу всегда; остальным — опубликованная и не удалённая (скрытая — по прямой ссылке видна). `fork` — новая стратегия владельца с черновиком = текст версии, `forked_from_version_id`; у удалённой — 404. `hide` / `unhide` — владелец.

**Тесты:** `VersionImmutabilityTest` (INV-5: смена `source` и снятие публикации через JDBC → исключение); `errorsBlockVersion422`; `publishOnceAndEvent`; `forkKeepsSourceLink`; `hiddenVisibleByDirectLink`; `referenceSeedPresent` (id, `published`, 6 параметров, текст совпадает с `testdata/dsl/reference.lab` из `core` — копия в `src/test/resources/workshop/reference.lab`).

### Задача 41: workshop: запросы на удаление и модерация

- **Размер:** S. **Волна:** 6. **Зависит от:** 39. **Связано:** ФТ-15, UC-23, `decisions.md` («Мастерская: скрытие и удаление», «Учётные записи»).

**Files:** Create: `src/main/resources/db/migration/V6__workshop_deletion_requests.sql` (`workshop.deletion_requests(id uuid pk, strategy_id uuid not null references workshop.strategies(id), requester_id uuid not null, reason text not null check (length(reason) between 1 and 2000), status text not null check (status in ('PENDING','APPROVED','REJECTED')), moderator_id uuid, comment text, created_at timestamptz not null default now(), decided_at timestamptz)`), `workshop/internal/ModerationService.java`, `workshop/web/ModerationController.java`; тест `workshop/web/ModerationApiTest.java`.

Поведение: запрос подаёт любой вошедший; список и решения — `@PreAuthorize("hasRole('MODERATOR')")`; `approve` → `deleted = true` у стратегии (строки версий не трогаются, INV-5).

**Тесты:** `userCannotListRequests403`; `approveMarksDeleted`; `deletedVersionHiddenFromOthers` (404 для не-модератора, 200 для модератора); `rejectKeepsStrategy`.

### Задача 42: analysis: отчёты и история

- **Размер:** M. **Волна:** 7. **Зависит от:** 36, 40. **Связано:** ФТ-2, ФТ-17, ФТ-21, ФТ-24, НФТ-3, UC-8, UC-10, UC-15.

**Files:** Create: `src/main/resources/db/migration/V10__analysis_reports.sql` (`analysis.reports(id uuid pk, subject_type text not null check (subject_type in ('SESSION','RUN')), subject_id uuid not null, owner_id uuid, level text not null, report jsonb not null, created_at timestamptz not null default now(), unique (subject_type, subject_id))`), `analysis/internal/{ReportListener,ReportJsonMapper,ReportRepository,HistoryService}.java`, `analysis/web/{ReportController,HistoryController}.java`; тесты `analysis/internal/ReportJsonMapperTest.java`, `analysis/web/{ReportApiTest,HistoryApiTest}.java`.

Поведение: `SessionFinished` и `RunCompleted` → `ReportJsonMapper` (proto `Report` + `CostBreakdown` + метаданные: снапшот через `MarketData.snapshot`, период и бумаги из `MarketSpec`, версия и параметры прогона, `reveal` для сессий) → JSON строго по схеме `Report` (деньги — строки `Decimals.toBigDecimal(...).toPlainString()` без лишних нулей, метрики — числа, пустые `optional` — `null`). Поле `double` в классах не заводится: метрики пишутся прямо в `ObjectNode`. История: `SessionQueries.listByOwner` + `RunQueries.listByOwner` (только `USER`) + `netReturn` из `report->'metrics'->>'totalReturn'` (`numeric`), новые первыми; заголовок — слепая незавершённая сессия «Слепая сессия от ДД.ММ.ГГГГ», завершённая — тикеры через запятую, прогон — «<стратегия> v<номер>».

**Тесты:** `ReportJsonMapperTest`: деньги `{1278446, 620000000}` → `"1278446.62"`; пустой `sharpe` → `null`; `reportStoredOnSessionFinished`; `reportMatchesContract`; `foreignReport404`; `historyBlindOnlyFilter` (ФТ-21); `historyNewestFirst`.

### Задача 43: analysis: разбор расхождений

- **Размер:** S. **Волна:** 8. **Зависит от:** 39, 42. **Связано:** ФТ-18, ФТ-19, ФТ-20, UC-9, `decisions.md` («Разбор расхождений»).

**Files:** Create: `src/main/resources/db/migration/V11__analysis_comparisons.sql` (`analysis.comparisons(id uuid pk, session_id uuid not null, owner_id uuid not null, version_ids jsonb not null, status text not null, result jsonb, error text, created_at timestamptz not null default now(), finished_at timestamptz)`), `analysis/internal/{ComparisonService,ComparisonJobHandler,ComparisonJsonMapper}.java`, `analysis/web/ComparisonController.java`; тест `analysis/web/ComparisonApiTest.java`.

Поведение: сессия своя и `FINISHED` (иначе 409 `CONFLICT`); `versionIds` пусто → эталон (`StrategyVersions.reference()`); больше 5 → 422; каждая версия видна пользователю. Задание `COMPARISON` → `analyzeDivergences(market, journal, last_step = cursor, алгоритмы с параметрами по умолчанию)` → JSON `Comparison`; `totalCost` — сумма цен ошибок при одном алгоритме, при нескольких — сумма `medianCost` консенсуса; `algorithmReports` — отчёты независимых портфелей.

`GET /api/comparisons/{id}` отдаёт сохранённый JSON как `JsonNode` (в нём `costPercent` — число; полей `double` в классах нет).

**Тесты:** `defaultUsesReference`; `moreThanFive422`; `unfinishedSession409`; `resultMappedWithConsensus`.

### Задача 44: analysis: рейтинг и каталог

- **Размер:** M. **Волна:** 7. **Зависит от:** 36, 39. **Связано:** ФТ-16, НФТ-2, UC-22, UC-24, INV-3, INV-4, `decisions.md` («Рейтинг»).

**Files:** Create: `src/main/resources/db/migration/V12__analysis_rating.sql`, `analysis/metrics/{RatingEpoch,RatingRow,RatingRepository,RatingAggregator}.java`, `analysis/internal/{RatingScheduler,RatingJobHandler,CatalogService}.java`, `analysis/web/CatalogController.java`; тесты `analysis/metrics/RatingAggregatorTest.java`, `analysis/internal/RatingSchedulerTest.java`, `analysis/web/CatalogApiTest.java`. Modify: `src/test/java/ru/ttsc/lab/MoneyTypesArchTest.java` (исключить `..analysis.metrics..`, `decisions.md`, «Деньги и округление», п. 11).

```sql
create table analysis.rating_epochs (id uuid primary key, snapshot_id uuid not null unique, seed bigint not null, windows jsonb not null, created_at timestamptz not null default now());
create table analysis.ratings (
  version_id uuid not null, epoch_id uuid not null references analysis.rating_epochs(id),
  status text not null check (status in ('PENDING','DONE','INVALID')), score double precision, by_regime jsonb,
  median_sharpe double precision, median_max_drawdown double precision, profitable_share double precision,
  invalid_reason text, run_ids jsonb not null default '[]', updated_at timestamptz not null default now(),
  primary key (version_id, epoch_id));
```

Поведение: эпоха — на последний снапшот (проверка при старте и раз в сутки); окна: `SplittableRandom(lab.rating.seed ^ snapshotId.getMostSignificantBits())`, 30 окон по 120 торговых дней, D1, начало — равномерно среди дней, от которых 120 дней помещаются, бумага — равномерно из пула слепого режима, покрывающая окно; список хранится в `windows`. Новая эпоха — пересчёт всех `publishedVisible()`; `VersionPublished` — пересчёт версии. Задание `RATING` → 30 `RunService.submit(purpose = RATING, параметры по умолчанию)`; по `RunCompleted` всех окон — агрегат: любой `INVALID` → `INVALID` с причиной; иначе `score` = медиана `totalReturn` (при чётном числе — среднее двух средних), режим окна по `benchmark_return`: > `regime-threshold` — `UP`, < −порога — `DOWN`, иначе (и без бенчмарка) — `FLAT`; медианы Sharpe (без пустых) и макс. просадки; доля окон с `totalReturn > 0`. Каталог: последняя опубликованная видимая версия каждой стратегии + рейтинг текущей эпохи; сортировка `score` по убыванию (пустые — в конце) или `newest`; `regime` — сортировка по `byRegime[regime].score`.

DTO `Rating` и `CatalogItem` — records в `analysis.metrics`; `GET /api/versions/{id}/rating` — рейтинг версии текущей эпохи (используется задачей 55).

**Тесты:** `RatingAggregatorTest`: доходности 0.1, −0.2, 0.3, 0.05 → `score == 0.075`; режимы по порогу 0.05 (0.06 → UP, −0.06 → DOWN, 0.01 → FLAT); один `INVALID` → `INVALID`. `RatingSchedulerTest`: одинаковый seed и снапшот → одинаковые окна; другой seed → другие. `CatalogApiTest`: скрытые и удалённые не видны; сортировка `score`.

---

## Трек frontend

Общее: фича — папка `src/app/features/<фича>/`, страница `<фича>-page.ts` (заглушку создала задача 6), состояние — сервис-хранилище на `signal`/`computed` (ADR-0009); HTTP — только через сгенерированный клиент (`src/app/core/api/generated`); тесты — Vitest + `TestBed` с `provideHttpClientTesting`; деньги — пайп `money` (задача 6), без арифметики. Тексты интерфейса — по-русски. Проверка — `npm run lint && npm test && npm run build` (PASS). «Готово, когда» — CI `frontend` зелёный, тесты из задачи есть.

### Задача 13: Вход и регистрация (уже в работе, task-list #9)

- **Волна:** 0. **Связано:** UC-1. Ветка `7-auth`: `features/auth`, `core/auth` (guard, CSRF). Задача 6 начинается после её влития (общие `app.routes.ts`, `app.config.ts`).

### Задача 63: Свечной график и кривая капитала (уже в работе, task-list #11)

- **Репозиторий:** frontend. **Волна:** 0. **Связано:** ФТ-6, ФТ-9, INV-1, INV-6, INV-7.
- Ветка `9-candle-chart`: `src/app/shared/chart/` — `CandleChartComponent` (`app-candle-chart`; входы `bars: ChartBar[]`, `markers: ChartMarker[]`, `blind`, `suspendedBarIndexes`), `EquityChartComponent` (`app-equity-chart`; `points: EquityPoint[]`, `blind`), `ChartBar {index, time | null, open, high, low, close, volume}` (строки), `ChartMarker {barIndex, side, label?, flagged?}`, `toDrawable()` — единственное превращение строки в число; `lightweight-charts` в `package.json`.
- **Готово, когда:** влито в `main`; задачи 46, 48, 50, 57 используют эти компоненты, своих графиков не пишут.

### Задача 45: Экран запуска ручной сессии

- **Размер:** S. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-1, ФТ-2, UC-2, `decisions.md` («Запуск сессии и прогона»).

**Files:** `features/session-new/{session-new-page.ts,session-new-page.html,session-new.store.ts,session-new-page.spec.ts}`.

Поведение: шаг — из `GET /marketdata/timeframes` (по умолчанию `D1`, если есть); длительность — 20 / 60 / 120 / 250, по умолчанию 60; начало — «Случайная закрытая дата» (по умолчанию) с числом бумаг 1…5 или «Своя дата» с датой и выбором до 5 тикеров из `GET /marketdata/instruments` и пометкой «Сессия будет неслепой»; `POST /sessions` → переход на `/sessions/:id`. Ошибки: `NO_PERIOD` — «Нет подходящего периода: уменьшите длительность или число бумаг»; `TOO_MANY_BARS` — «Слишком много свечей для ручной сессии: увеличьте шаг или уменьшите длительность».

**Тесты:** `defaultsAreD1And60Random`; `dateModeRequiresTickersAndWarnsNotBlind`; `submitNavigatesToArena`; `noPeriodMessage`.

### Задача 46: Арена: состояние, график, плеер

- **Размер:** M. **Волна:** 2. **Зависит от:** 6, 63. **Связано:** ФТ-5, ФТ-6, ФТ-11, НФТ-5, ADR-0002, ADR-0009, INV-1, INV-7, UC-3, UC-6.

**Files:** `features/arena/{arena-page.ts,arena-page.html,arena.store.ts,player-controls.ts,chart-mapping.ts,arena.store.spec.ts,arena-page.spec.ts,chart-mapping.spec.ts}`.

**Interfaces (Produces):**

```ts
// chart-mapping.ts — к компонентам задачи 63
function toChartBars(bars: BarView[]): ChartBar[];          // index = step, time = bar.time ?? null
function toChartMarkers(trades: TradeView[]): ChartMarker[]; // barIndex = step, flagged = stopAndTakeSameBar
function suspendedIndexes(bars: BarView[]): number[];       // шаги с afterHalt
// arena.store.ts
class ArenaStore {
  session: Signal<SessionView | null>; cursor: Signal<number>; playing: Signal<boolean>; speed: Signal<1 | 5 | 10>;
  selectedKey: WritableSignal<string>; barsOf(key: string): Signal<BarView[]>;
  load(id: string): Promise<void>; play(speed: 1 | 5 | 10): Promise<void>; pause(): Promise<void>; step(): Promise<void>;
  applyEvent(e: SessionEvent): void;   // step: дописать бары, заменить портфель, обновить заявки; если e.cursor > cursor + 1 — load(id)
}
```

Поведение: при открытии `load` (UC-6) и подписка `EventStream` на `/api/sessions/:id/events`; после переподключения — `load`; бары `afterHalt` — маркер «торги приостановлены»; заголовок бумаги — `label · sector` (в неслепой — и тикер); переключение бумаг — вкладками; кнопки ×1/×5/×10, пауза, шаг (шаг недоступен во время игры). Хранилище держит только то, что прислал сервер (INV-1): никаких запросов баров впереди курсора.

**Тесты:** `applyStepAppendsBarsAndPortfolio`; `gapInCursorTriggersReload`; `reconnectReloadsState`; `blindHeaderShowsLabelAndSectorOnly` (в DOM нет тикера); `stepDisabledWhilePlaying`; `chartLabelsDayNInBlind`.

### Задача 47: Арена: заявки, портфель, сделки

- **Размер:** M. **Волна:** 3. **Зависит от:** 46. **Связано:** ФТ-7, ФТ-9, ФТ-10, UC-4, UC-5, INV-2, INV-6, `decisions.md` («Заявки»).

**Files:** `features/arena/{order-ticket.ts,order-ticket.html,orders-list.ts,portfolio-panel.ts,trades-list.ts,orders.service.ts,order-ticket.spec.ts,orders.service.spec.ts}`.

Поведение: тикет — бумага, сторона, тип (7 типов ФТ-7), лоты, поля цены по типу (лимит; стоп; лимит и стоп; трейлинг %), срок «день» / «до отмены», флажок OCO со второй ногой; `seenStep = store.cursor()`; `clientOrderId = crypto.randomUUID()` один на попытку, при сетевой ошибке повтор с тем же id (ревью, п. 1); отказ — текст по `reason` (`INSUFFICIENT_CASH` — «Не хватает денег», `INSUFFICIENT_POSITION` — «Нет столько бумаг», `INVALID_PARAMS` — «Проверьте поле …», `LIQUIDITY_LIMIT` — «Не хватило ликвидности»). Список активных заявок — «Отменить», «Изменить» (тикет в режиме замены). Портфель — деньги, стоимость, позиции; сделки — с меткой «стоп раньше тейка» при `stopAndTakeSameBar`.

**Тесты:** `retryKeepsClientOrderId`; `seenStepIsCursor`; `requiredFieldsByType` (у `STOP_LIMIT` обязательны обе цены); `replaceSendsReplaceRequest`; `rejectionMessages`.

### Задача 48: Отчёт

- **Размер:** M. **Волна:** 2. **Зависит от:** 6, 63. **Связано:** ФТ-2, ФТ-17, ФТ-24, UC-8, UC-15.

**Files:** `features/report/{report-page.ts,report-view.ts,report-view.html,cost-breakdown.ts,comparison-dialog.ts,report-view.spec.ts,comparison-dialog.spec.ts}` (кривая капитала — `app-equity-chart` задачи 63).

**Interfaces (Produces):** `ReportView` — standalone-компонент `@Input() report: Report`, используется задачей 57.

Поведение: блок раскрытия (период, тикеры, названия); метрики (пустые — «—», доли — в %, 2 знака); кривая капитала; издержки по видам; цепочка «наивный → … → честный» таблицей с вкладом фактора (разность соседних `netReturn`) и флагами («издержки съели больше половины прибыли», «знак результата сменился», «Sharpe > 3 — подозрительно»); находки и уровень проверки; метаданные воспроизводимости. Для сессии — кнопка «Разобрать расхождения»: диалог выбора до 5 версий из каталога (пусто — эталон) → `POST /sessions/:id/comparisons` → `/sessions/:id/comparisons/:comparisonId`.

**Тесты:** `nullMetricShowsDash`; `breakdownContributions` (netReturn 0.2, 0.18, 0.15, 0.14, 0.12, 0.10 → вклады −0.02, −0.03, −0.01, −0.02, −0.02); `flagsTexts`; `dialogLimitsFive`; `emptySelectionMeansReference`.

### Задача 49: Разбор расхождений

- **Размер:** M. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-18, ФТ-19, ФТ-20, UC-9.

**Files:** `features/comparison/{comparison-page.ts,comparison-page.html,comparison.store.ts,consensus-text.ts,comparison.store.spec.ts,consensus-text.spec.ts}`.

Поведение: опрос `GET /comparisons/:id` каждые 2 с до `DONE` / `FAILED`; таблица расхождений по убыванию |цены ошибки|: тип («Лишнее действие», «Упущенное действие», «Размер», «Момент» с Δ шагов), шаги, лоты, цена ошибки (> 0 — красным: «как алгоритм было бы выгоднее»), причина; итог; консенсус; «Прибыльные сделки, которые алгоритм пропустил» со ссылкой «Написать правило» → `/workshop` (UC-9, 6а); кривые капитала независимых портфелей.

**Тесты:** `consensusText`: действие человека «покупка», `agreeing = 1`, `total = 5` → «4 из 5 здесь не покупали бы»; упущенное «продажа», 3 из 5 → «3 из 5 здесь продавали бы»; `pollingStopsOnDone`; `sortedByAbsCost`.

### Задача 50: Воспроизведение сессии и прогона

- **Размер:** S. **Волна:** 2. **Зависит от:** 6, 63. **Связано:** ФТ-11, UC-11, `decisions.md` («Плеер и воспроизведение»).

**Files:** `features/replay/{replay-page.ts,replay-page.html,replay.store.ts,replay.store.spec.ts}`.

Поведение: `GET /sessions/:id/replay` или `/runs/:id/replay`; локальный плеер по загруженным данным (данные раскрыты): индекс шага, ×1/×5/×10 (1, 5, 10 шагов в секунду), пауза, шаг; график `app-candle-chart` (задача 63) с маркерами сделок до текущего шага.

**Тесты:** `stepAdvancesIndex`; `speedTickInterval` (×5 → 200 мс); `markersUpToIndex`.

### Задача 51: История

- **Размер:** S. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-21, UC-10.

**Files:** `features/history/{history-page.ts,history-page.html,history.store.ts,history-page.spec.ts}`.

Поведение: `GET /history` с фильтрами «только слепые» и «сессии / прогоны»; колонки — дата, режим, название, итог, статус, метка «неслепая»; действия — отчёт, продолжить (незавершённая сессия), воспроизвести, повторить прогон (`POST /runs/:id/repeat` → `/runs/:newId`).

**Тесты:** `blindOnlyQueryParam`; `notBlindBadge`; `continueOnlyForActive`.

### Задача 53: Мастерская: список стратегий и редактор

- **Размер:** M. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-12, ФТ-13, ФТ-14, UC-12, UC-13, `dsl.md`.

**Files:** `features/workshop/{workshop-page.ts,workshop-page.html,strategy-editor.ts,dsl-language.ts,diagnostics.ts,workshop.store.ts,diagnostics.spec.ts,workshop.store.spec.ts}`.

**Interfaces:** `toOffset(doc: string, line: number, column: number): number` (строки и столбцы с 1, столбцы — кодовые точки); `applyFix(doc: string, edits: TextEdit[]): string` (правки применяются с конца документа).

Поведение: `/workshop` — свои стратегии и «Новая»; `/workshop/:strategyId` — CodeMirror с подсветкой ключевых слов `dsl.md`; через 500 мс после правки — `POST /strategies/check` → диагностики в `@codemirror/lint` (ошибки красным, `L001` и `W-LA01` — жёлтым, у `L001` действие «Вынести в параметр» — `applyFix`); автосохранение черновика через 2 с без правок (`PUT draft`); «Создать версию» (`POST versions`; 422 — показать диагностики); список версий со ссылками на `/versions/:id`. Сводка уровня проверки: OK / предупреждение / ошибка (ФТ-14).

**Тесты:** `toOffsetMultiline`; `applyFixInsertsParamAndReplacesLiteral` (`sma(close, 20)` + исправление `L001` → текст с `param sma_n = 20` и `sma(close, sma_n)`); `checkDebounced500ms`; `autosaveAfterIdle`.

### Задача 55: Карточка версии и запуск прогона

- **Размер:** M. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-1, ФТ-13, ФТ-15, ФТ-22, ФТ-23, UC-14, UC-16, UC-17, UC-19, UC-20, UC-21, UC-23.

**Files:** `features/version/{version-page.ts,version-page.html,run-form.ts,walk-forward-form.ts,version.store.ts,run-form.spec.ts,version-page.spec.ts}`.

Поведение: текст (только чтение), автор («Платформа» у эталона), параметры с диапазонами, предупреждения линтера (число — на карточке, ФТ-13), рейтинг по режимам (`GET /versions/:id/rating`, отдельно от карточки); действия: «Опубликовать» (владелец), «Форк» (имя), «Скрыть» / «Вернуть в каталог» (владелец), «Запросить удаление» (причина). Форма прогона: параметры (проверка диапазона на клиенте), шаг, длительность в торговых днях, начало, стресс — нет / параметрический (X, k, N, q, шаг начала) / пресет («24.02.2022», «март 2020») → `POST /runs` → `/runs/:id`. Форма walk-forward: даты, до 5 тикеров, шаг → `POST /walk-forwards` → `/walk-forwards/:id`.

**Тесты:** `paramOutOfRangeBlocksSubmit`; `presetHidesParametricFields`; `ownerActionsOnlyForOwner`; `forkNavigatesToWorkshop`.

### Задача 56: Каталог

- **Размер:** S. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-16, UC-22.

**Files:** `features/catalog/{catalog-page.ts,catalog-page.html,catalog.store.ts,catalog-page.spec.ts}`.

Поведение: `GET /catalog`, сортировка «по рейтингу» / «новые», фильтр режима рынка («рост», «падение», «боковик»); карточка — название, автор, версия, оценка (медиана доходности, %), число предупреждений линтера; клик → `/versions/:id`.

**Тесты:** `regimeQueryParam`; `ratingPendingShowsDash`.

### Задача 57: Прогон и walk-forward

- **Размер:** M. **Волна:** 3. **Зависит от:** 48. **Связано:** ФТ-14, ФТ-17, ФТ-22, ФТ-23, ФТ-24, НФТ-2, UC-14, UC-15, UC-16, UC-17, UC-18.

**Files:** `features/run/{run-page.ts,run-page.html,run.store.ts,walk-forward-page.ts,walk-forward.store.ts,run.store.spec.ts,walk-forward.store.spec.ts}`.

Поведение: `/runs/:id` — прогресс по SSE (`progress`, `completed`; после `completed` — `GET /runs/:id/report`), уровень проверки и находки; `ReportView`; при стресс-паре — два отчёта рядом и метка начала события на кривой; «Повторить» и бейдж «совпадает» / «не совпадает» по `repeatMatches`. `/walk-forwards/:id` — опрос раз в 2 с, таблица отрезков (окна, выбранные параметры, доходность подбора и проверки, ссылка на отчёт), итог по цепочке.

**Тесты:** `progressFromSse`; `loadsReportOnCompleted`; `stressPairSideBySide`; `walkForwardPollingStops`.

### Задача 58: Модерация

- **Размер:** S. **Волна:** 2. **Зависит от:** 6. **Связано:** ФТ-15, UC-23.

**Files:** `features/moderation/{moderation-page.ts,moderation-page.html,moderation-page.spec.ts}`.

Поведение: пункт меню и страница — только у роли `MODERATOR` (`GET /me`); список запросов `PENDING`; «Удалить» / «Отклонить» с комментарием.

**Тесты:** `hiddenForUser`; `approveCallsApi`.

---

## Трек docs-infra

### Задача 52: Окружение: воркер в Docker Compose

- **Репозиторий:** backend. **Размер:** S. **Волна:** 6. **Зависит от:** 25, 34, 62, DI. **Связано:** INV-10, НФТ-6, ADR-0005, ADR-0007.

**Files:** Modify: `backend/deploy/docker-compose.yml` (сервис `worker`: `build: ../../core`, переменные `CLICKHOUSE_URL=http://clickhouse:8123`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, без `ports`; `backend` — `LAB_WORKER_HOST=worker`, `LAB_CLICKHOUSE_URL`; сервис `caddy` — образ фронтенда `build: ../../frontend` с `Caddyfile` из `deploy/`), `backend/deploy/.env.example`, `backend/.github/workflows/ci.yml` (шаг проверки портов), `backend/AGENTS.md` («Команды»). Create: `backend/deploy/tests/compose-ports.sh`.

`compose-ports.sh`: `docker compose -f deploy/docker-compose.yml config --format json` → у всех сервисов, кроме `caddy`, нет `ports` (INV-10); иначе выход 1 со списком.

- [ ] Тест: `compose-ports.sh` — PASS на итоговом файле и FAIL на копии, где у `postgres` есть `ports`.
- **Готово, когда:** `docker compose up -d --build` поднимает все сервисы; CI `backend` проверяет порты.

### Задача 61: Сквозной сценарий (ходячий скелет) и интеграция с ClickHouse

- **Репозиторий:** backend. **Размер:** S. **Волна:** 7. **Зависит от:** 31, 32, 46, 52. **Связано:** ФТ-1, ФТ-6, ФТ-7, ФТ-11, INV-1, INV-2, INV-8.

**Files:** Create: `backend/deploy/tests/smoke.sh`, `backend/.github/workflows/e2e.yml` (`workflow_dispatch` и ночной запуск; клонирует `core` и `frontend` рядом).

`smoke.sh` (на окружении из задачи 52 с фикстурой DI): регистрация и вход (cookie, CSRF) → `POST /api/sessions` с началом DATE и тикерами фикстуры → `POST /orders` рыночная покупка 1 лота с `seenStep = 0` → два `POST /step` → `GET /api/sessions/{id}`: одна сделка на шаге 1 (INV-2), `cursor == 2`, баров с `step > 2` нет (INV-1) → перезапуск контейнера `backend` → `GET` даёт то же состояние (INV-8) → `POST /finish` → `GET /report` — 200.

- **Готово, когда:** сценарий проходит локально и в `e2e.yml`; ClickHouse-чтение воркера (задачи 34, 62) проверено на настоящей базе.

### Задача 54: Документы после реализации

- **Репозиторий:** documentation. **Размер:** S. **Волна:** 9. **Зависит от:** все задачи, проверки которых перечислены в таблице INV ниже. **Связано:** `workflow.md` («Когда обновлять документы»).

**Files:** Modify: `invariants.md` (колонка «Проверка» — по таблице «Инварианты → тесты»), `architecture.md` (RPC воркера и что он не хранит состояние; модули backend, включая `worker` и `config`, граф зависимостей из преамбулы трека backend вместо строки «Связи», события `SessionEndReached`, `SessionFinished`, `RunCompleted`, `VersionPublished`; очередь заданий), `status.md` («Где мы»), `AGENTS.md` (строка про `plans/`).

- **Готово, когда:** каждая строка таблиц ниже указывает на существующий тест.

---

## Сводка волн

| Волна | core | backend | frontend | docs-infra |
|---|---|---|---|---|
| 0 | 5*, 34* | 2, 12*, DI* | 13*, 63* | — |
| 1 | 1, 3 | — | 6 | — |
| 2 | 7, 8, 9, 10 | 4 | 45, 46, 48, 49, 50, 51, 53, 55, 56, 58 | — |
| 3 | 11, 18, 19, 22, 23, 26 | 17, 33, 35 | 47, 57 | — |
| 4 | 14, 15, 16, 20, 24, 62 | 30, 38 | — | — |
| 5 | 21, 25 | 31, 32, 39 | — | — |
| 6 | 27, 28, 29 | 36, 40, 41 | — | 52 |
| 7 | 59 | 37, 42, 44, 60 | — | 61 |
| 8 | — | 43 | — | — |
| 9 | — | — | — | 54 |

\* — уже в работе. Ходячий скелет: 1 → 3 → 7, 8 → 11 → 15 → 23 → 25 (+ 62) → 33, 17 → 30 → 31, 32 → 46, 47 → 52 → 61; это первый приоритет внутри каждой волны.

Межрепозиторные зависимости — только через контракты: backend зависит от `core` через задачу 1 (proto), frontend от backend — через задачу 2 (OpenAPI); реализация воркера нужна backend только в сквозном тесте 61. Тесты backend и frontend работают с подменой воркера и API.

## Инварианты → тесты

| INV | Задача и тест |
|---|---|
| INV-1 | 15 `Replay.NoFutureBars`; 25 `ReplaySession.UpToStepNoFuture`; 31 `stepEventBarsOnlyAtCursor`; 46 (хранилище не запрашивает будущее); 61 |
| INV-2 | 11 `MarketOrders.NotBeforeNextBar`; 15 `Replay.OrderExecutesNextBar`; 32 `journaledAtCursorNotSeenStep`; 61; исключение — наивный прогон, 27 |
| INV-3 | 21 `Backtest.SameEngineAsHuman`; 27 `CostBreakdown.LastEqualsHonestRun`; 29 (V алгоритма — тем же движком) |
| INV-4 | 3 `BuildFlags.NoFusedMultiplyAdd`; 21 `Determinism.SameDigestTwice`; 59 (одинаковый `digest`); 60 `sameDigestMatches`; 44 `RatingSchedulerTest` |
| INV-5 | 39 `VersionImmutabilityTest`; DI (снапшоты не дописываются) |
| INV-6 | 5 (тесты `Decimal`); 16 эталонный портфель; 33 `DecimalsTest`; 42 `ReportJsonMapperTest`; `MoneyTypesArchTest` (4, 44) |
| INV-7 | 30 `BlindContractTest`; 40 `revealOnlyAfterFinish`; 46 `blindHeaderShowsLabelAndSectorOnly` |
| INV-8 | 15 `Replay.Deterministic`; 30 `JournalImmutabilityTest`; 31 `restartOpensPaused`; 61 (перезапуск backend) |
| INV-9 | 18 `Checker.NoNewsAccess` |
| INV-10 | 52 `compose-ports.sh`; 17 (ClickHouse только `SELECT`) |

## ФТ и НФТ → задачи

| Требование | Задачи |
|---|---|
| ФТ-1 запуск | 17, 30, 36, 45, 55 |
| ФТ-2 слепой режим | 17, 30, 40, 46 |
| ФТ-3 архив, свечи 1 с – 1 д | DI, 34, 62, 7, 17 |
| ФТ-4 снапшоты | DI, 17, 42 (метаданные) |
| ФТ-5 календарь, разрывы | DI, 7, 62, 46, 63 |
| ФТ-6 плеер | 15, 25, 31, 46, 63 |
| ФТ-7 типы заявок | 11, 14, 32, 47 |
| ФТ-8 общая модель | 11, 21 |
| ФТ-9 частичное, стоп раньше тейка | 11, 14, 47 |
| ФТ-10 портфель, остановка | 8, 15, 40 |
| ФТ-11 журнал, восстановление | 15, 25, 30, 31, 32, 50 |
| ФТ-12 DSL, `because` | 9, 18, 20, 53 |
| ФТ-13 линтер | 19, 24, 53, 55 |
| ФТ-14 чтение будущего | 18, 21, 24, 59, 53 |
| ФТ-15 публикация, версии | 39, 41, 55, 58 |
| ФТ-16 каталог, рейтинг | 44, 56 |
| ФТ-17 метрики | 22, 25, 42, 48 |
| ФТ-18 человек против алгоритма, консенсус | 29, 43, 49 |
| ФТ-19 расхождения | 20, 29, 43, 49 |
| ФТ-20 цена ошибки, пропущенные сделки | 29, 43, 49 |
| ФТ-21 история | 42, 51 |
| ФТ-22 walk-forward | 28, 37, 55, 57 |
| ФТ-23 стресс | 26, 36, 59, 55, 57 |
| ФТ-24 наивный и честный | 27, 59, 48 |
| НФТ-1 честность времени | см. INV-1, INV-2 |
| НФТ-2 детерминизм | 3, 21, 59, 60 |
| НФТ-3 воспроизводимость | 36 (`market`, версия, параметры), 42 (метаданные), 60 |
| НФТ-4 точность | 5, 16, 22, 33 |
| НФТ-5 устойчивость | 15, 31, 35, 36, 46 |
| НФТ-6 SSE, REST, HTTPS | 2, 31, 36, 52 |

## Открытые вопросы плана

Решить до начала соответствующих задач; до решения — делать, как написано выше.
1. Утечка уровня цены в слепом режиме: суммы в рублях реальные, поэтому `marketValue / lots` даёт реальную цену лота (задача 30). Варианты: показывать суммы в масштабе слепых цен или скрывать стоимость позиций до конца сессии — решает команда.
2. IMOEX пока не импортируется: `benchmark_return` пустой, режим рейтинга — всегда «боковик» (задачи 22, 44). Нужна задача импорта IMOEX (ISS, `engine=stock&market=index`).
3. Формулы метрик (безрисковая ставка 0, 252 дня, выборочное стандартное отклонение) и правило `afterHalt` (15 минут) — предложения плана; при изменении правятся задачи 7 и 22 и `decisions.md`.
4. Несколько снапшотов с пересекающимися периодами (`status.md`, вопрос 3): план берёт последний готовый снапшот.
