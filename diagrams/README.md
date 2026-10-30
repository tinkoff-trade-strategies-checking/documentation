# Диаграммы

PlantUML-исходники к `../use-cases.md`. Обновляются вместе с юзкейсами: изменился UC — поправь диаграмму в том же PR.

| Файл | Что |
|---|---|
| `use-cases-overview.puml` | все UC по областям и акторы, без include/extend |
| `use-cases-arena.puml` | арена: ручная торговля, связи include/extend |
| `use-cases-workshop.puml` | мастерская: алгоритмы, публикация, рейтинг |
| `use-cases-data.puml` | подготовка данных и новости |
| `_style.iuml` | общий стиль; серые UC со стереотипом «развитие» — вне ФТ-1–21 |

Связи «запускает», «использует», «строит отчёт» — не стандартный UML, а пометки для команды.

## Как посмотреть

Диаграммы раскладываются встроенным движком (`!pragma layout smetana`), Graphviz не нужен. Нужен PlantUML 1.2025 или новее: на 1.2024 диаграмма арены падает.

```sh
java -jar plantuml.jar -charset UTF-8 -tsvg diagrams/use-cases-*.puml
```

Или плагин PlantUML в IDE, или https://www.plantuml.com/plantuml (вставить исходник вместе с содержимым `_style.iuml`).
