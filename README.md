# Т-Инвестиции: тренажёр и лаборатория стратегий

Тренажёр трейдера и лаборатория стратегий на истории Московской биржи. Документация проекта:

- [Требования](requirements.md) — ФТ и НФТ
- [Юзкейсы](use-cases.md) — акторы и сценарии, пробелы в требованиях
- [Инварианты](invariants.md) — что нельзя нарушать
- [Продуктовые решения](decisions.md)
- [DSL стратегий](dsl.md)
- [Архитектура](architecture.md)
- [ADR](adr/README.md)
- [Статус и открытые вопросы](status.md)
- [Как ведём работу](workflow.md) — доска задач, issue, PR
- [Wiki](https://github.com/tinkoff-trade-strategies-checking/documentation/wiki): Vision, Глоссарий

Код: [frontend](https://github.com/tinkoff-trade-strategies-checking/frontend), [backend](https://github.com/tinkoff-trade-strategies-checking/backend), [core](https://github.com/tinkoff-trade-strategies-checking/core).

## Рабочее пространство

Клонируйте все четыре репозитория в одну папку, тогда ссылки `../documentation/` из `AGENTS.md` кодовых репозиториев будут работать:

```sh
for r in documentation frontend backend core; do
  git clone https://github.com/tinkoff-trade-strategies-checking/$r.git
done
```
