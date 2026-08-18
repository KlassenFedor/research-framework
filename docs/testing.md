# Тестовый контракт MVP

Тесты написаны до реализации основных слоёв и являются исполняемой
спецификацией архитектуры. Неподдерживаемое поведение не скрывается через
`xfail`; platform-specific symlink checks пропускаются только там, где ОС не
предоставляет symlinks.

## Покрытие требований

| Область | Зафиксированное поведение |
|---|---|
| Domain | Все типы Node, Actor, enum, неизменяемость, ошибки |
| Relations | Полная матрица source/kind/target, `supersedes`, `related_to` |
| Graph | ID/alias/prefix, индексы, filters, neighbors, BFS, shortest path, JSON |
| Markdown codec | Golden files, body round-trip, порядок полей, restricted YAML 1.2 |
| JSON Schema | Draft 2020-12, package resources, все Node kinds, config, enums и negative cases |
| Discovery | Поиск от вложенного пути, границы vault, symlinks, детерминизм |
| Validation | Syntax, structural, referential, semantic и graph diagnostics |
| Storage | Candidate prevalidation, atomic write/rollback, revision conflict, локальность diff, защита путей |
| Formatting | Read-only check, canonical front matter, byte-exact body, idempotence, rollback, concurrent edits |
| Python API | Init/open, atomic mutations, operation diagnostics, snapshots |
| CLI | Human/JSON warnings, таблицы/графы, `$EDITOR`, initial relations, stdin и exit codes |
| Git acceptance | Реальные diff для create/update/link/remove/archive/format и локальность файлов |
| End-to-end | `init → create → link → reopen → traverse → validate → export` |

## Fixture-проект

`tests/fixtures/example_project` содержит все десять типов Node, два Evidence с
разным эпистемическим направлением, Run, Assessment и Decision. В нём 11 узлов
и 14 типизированных связей. Fixture должен проходить validation без warnings.

`PROJECT.md` намеренно не имеет front matter: он проверяет, что обзорный
человеческий документ не принимается за Node.

## Restricted YAML

Физический формат допускает удобные человеку списки, mappings, комментарии и
многострочные scalars. Семантическая модель остаётся JSON-совместимой.

Запрещены:

- пользовательские YAML tags;
- anchors, aliases и merge keys;
- сложные keys и YAML sets;
- дублирующиеся keys;
- неявные YAML 1.1 boolean вроде `on` и `yes`;
- timestamps без часового пояса на уровне доменной схемы.

## Текущий статус

На 2026-08-18 pytest собирает и успешно выполняет 408 сценариев:

```text
408 passed
```

Branch coverage составляет 70,00% при обязательном пороге 70%. CLI contract
tests запускают отдельный процесс и поэтому не входят в coverage родительского
процесса. Дополнительно
проходят strict mypy, Ruff, Ruff format check, `compileall`, сборка пакета и
smoke-test установленного `rf` entrypoint.
