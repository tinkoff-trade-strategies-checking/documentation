# Т-Инвестиции: тренажёр и лаборатория стратегий

Тренажёр трейдера и лаборатория стратегий на истории Московской биржи. Документация проекта:

- [Требования](requirements.md) — ФТ и НФТ
- [Инварианты](invariants.md) — что нельзя нарушать
- [Продуктовые решения](decisions.md)
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

## ИИ-агенты

Инструкции для агентов — `AGENTS.md` в корне каждого репозитория; общие правила проекта — `documentation/AGENTS.md`, `workflow.md`, `invariants.md`. Не создавайте `CLAUDE.md` рядом с `AGENTS.md`: Claude Code и opencode тогда перестанут читать `AGENTS.md` или прочитают только один из файлов.

| Агент | Инструкции | Скиллы |
|---|---|---|
| Claude Code (с v2.1.277) | `AGENTS.md`, если в папке запуска и выше нет `CLAUDE.md` | `.claude/skills/` |
| Codex | `AGENTS.md` от корня репозитория до папки запуска | `.agents/skills/` |
| opencode | ближайший `AGENTS.md` вверх от папки запуска | `.agents/skills/`, `.claude/skills/`, `.opencode/skills/` |

Скилл для Miro-доски — `.agents/skills/miro-board/`. Claude Code не читает `.agents/`, поэтому для него есть переходник `.claude/skills/miro-board-claude/`; в opencode он скрыт через `opencode.json`, чтобы скилл не появлялся дважды.
