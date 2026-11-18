# Т-Инвестиции: тренажёр и лаборатория стратегий

Тренажёр трейдера и лаборатория стратегий на истории Московской биржи. Здесь — продуктовая документация: что строим, почему так и что нельзя ломать. Код — в [frontend](https://github.com/tinkoff-trade-strategies-checking/frontend), [backend](https://github.com/tinkoff-trade-strategies-checking/backend), [core](https://github.com/tinkoff-trade-strategies-checking/core), [dsl](https://github.com/tinkoff-trade-strategies-checking/dsl); процесс работы и настройки ИИ-агентов — в [home](https://github.com/tinkoff-trade-strategies-checking/home).

- [Требования](requirements.md) — ФТ и НФТ
- [Юзкейсы](use-cases.md) — акторы и сценарии, пробелы в требованиях
- [Инварианты](invariants.md) — что нельзя нарушать
- [Продуктовые решения](decisions.md)
- [DSL стратегий](dsl.md)
- [Архитектура](architecture.md)
- [Wiki](https://github.com/tinkoff-trade-strategies-checking/documentation/wiki): Vision, Глоссарий

Код: [frontend](https://github.com/tinkoff-trade-strategies-checking/frontend), [backend](https://github.com/tinkoff-trade-strategies-checking/backend), [core](https://github.com/tinkoff-trade-strategies-checking/core), [DSL](https://github.com/tinkoff-trade-strategies-checking/dsl).


## Проверка ссылок на тесты инвариантов

`scripts/check-invariants.py` проверяет, что тесты из колонки «Проверка» в `invariants.md` существуют в `core` и `frontend`. Нужен Python 3, `core` и `frontend` лежат рядом с `documentation`:

```
python3 scripts/check-invariants.py [--core ../core] [--frontend ../frontend]
```

Ненайденные ссылки печатаются как `INV-N → ссылка`, код выхода 1. В CI — `.github/workflows/invariants.yml` (наблюдение, не обязательная проверка).

## Правила правки

- Приоритет источников: `requirements.md` > `invariants.md` > `decisions.md` > wiki. Нашли противоречие — исправьте младший документ или спросите команду, не выбирайте молча.
- ID (ФТ-N, НФТ-N, INV-N, UC-N) стабильны: на них ссылаются код и задачи. Номера не переиспользуются; отменённое помечается, а не удаляется.
- Архитектурные решения — раздел «Архитектура» в `decisions.md`; изменить принятое — явно, с причиной, в PR, а не молча.
- Решённый вопрос из `status.md` переносится в `decisions.md`.
- Документ правится в том же PR, что и изменение, которое сделало его неверным (таблица «Когда обновлять документы» в [home/workflow.md](https://github.com/tinkoff-trade-strategies-checking/home/blob/main/workflow.md)).

Задачи и их ход — на [доске](https://github.com/orgs/tinkoff-trade-strategies-checking/projects/2) и в issue, не в этих файлах.
