# Т-Инвестиции: тренажёр и лаборатория стратегий

Тренажёр трейдера и лаборатория стратегий на истории Московской биржи. Здесь — продуктовая документация: что строим, почему так и что нельзя ломать. Код — в [frontend](https://github.com/tinkoff-trade-strategies-checking/frontend), [backend](https://github.com/tinkoff-trade-strategies-checking/backend), [core](https://github.com/tinkoff-trade-strategies-checking/core), [dsl](https://github.com/tinkoff-trade-strategies-checking/dsl); процесс работы и настройки ИИ-агентов — в [home](https://github.com/tinkoff-trade-strategies-checking/home).

## Карта

| Документ | Что | Когда читать |
|---|---|---|
| [invariants.md](invariants.md) | INV-1…10: правила, нарушение которых ломает продукт | перед любой правкой исполнения, данных, слепого режима, денег |
| [requirements.md](requirements.md) | ФТ-1…24, НФТ-1…6, границы продукта | при работе над фичей — найти её ФТ |
| [use-cases.md](use-cases.md) | UC-1…30: акторы, сценарии, покрытие ФТ; диаграммы — [diagrams/](diagrams/README.md) | при проектировании фичи и экрана |
| [decisions.md](decisions.md) | продуктовые детали сверх требований | когда требование допускает разные толкования |
| [dsl.md](dsl.md) | язык стратегий: грамматика, функции, линтер, проверка на чтение будущего | при работе над мастерской и исполнением стратегий |
| [architecture.md](architecture.md) | компоненты, Java-модули, хранилища, связи | при изменении на стыке компонентов |
| [adr/](adr/README.md) | архитектурные решения с причинами | перед тем как менять устоявшийся подход |
| [status.md](status.md) | сроки, текущее состояние, открытые вопросы | в начале работы над новым блоком |
| [Wiki](https://github.com/tinkoff-trade-strategies-checking/documentation/wiki) | Vision (ранняя версия продукта, до 21.10.2026), Глоссарий | термины рынка, данных, исполнения и метрик |

ФТ, НФТ, INV, UC, ADR ищите по ID (`ФТ-7`, `INV-4`, `UC-9`, `ADR-0007`), а не читая документы целиком.

## Правила правки

- Приоритет источников: `requirements.md` > `invariants.md` > `decisions.md` > wiki. Нашли противоречие — исправьте младший документ или спросите команду, не выбирайте молча.
- ID (ФТ-N, НФТ-N, INV-N, UC-N, ADR-NNNN) стабильны: на них ссылаются код и задачи. Номера не переиспользуются; отменённое помечается, а не удаляется.
- Принятый ADR не переписывается — новое решение оформляется новым ADR.
- Решённый вопрос из `status.md` переносится в `decisions.md` или ADR.
- Документ правится в том же PR, что и изменение, которое сделало его неверным (таблица «Когда обновлять документы» в [home/workflow.md](https://github.com/tinkoff-trade-strategies-checking/home/blob/main/workflow.md)).
- Пишем по-русски, коротко, без воды. Каждое утверждение опирается на решение команды, а не на догадку.

Задачи и их ход — на [доске](https://github.com/orgs/tinkoff-trade-strategies-checking/projects/2) и в issue, не в этих файлах.
