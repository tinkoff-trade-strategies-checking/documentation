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
- [Как ведём работу](https://github.com/tinkoff-trade-strategies-checking/home/blob/main/workflow.md) — доска задач, issue, PR (в репозитории `home`)
- [Wiki](https://github.com/tinkoff-trade-strategies-checking/documentation/wiki): Vision, Глоссарий

Код: [frontend](https://github.com/tinkoff-trade-strategies-checking/frontend), [backend](https://github.com/tinkoff-trade-strategies-checking/backend), [core](https://github.com/tinkoff-trade-strategies-checking/core).

## Рабочее пространство

Все репозитории клонируются рядом, в одну папку — проще всего через `home`:

```sh
git clone https://github.com/tinkoff-trade-strategies-checking/home.git
cd home && sh scripts/clone-repos.sh
```

## ИИ-агенты

Агенты запускаются из репозитория [home](https://github.com/tinkoff-trade-strategies-checking/home): там указатели на все репозитории, процесс работы, общие скиллы (в том числе для Miro-доски) и инструкции, как запускать Claude Code, Codex и opencode. Здесь — только продуктовые знания; карта для агентов — `AGENTS.md`.
