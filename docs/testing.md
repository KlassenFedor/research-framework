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
| Graph | ID/alias/prefix, индексы, filters, neighbors, BFS, linear-memory shortest path, JSON, глубокие cycles без recursion |
| HTML graph | Full/local view, safe embedding, tag filters, Anchor-компоненты, linked visibility, hidden details, bounded layout и progress |
| Markdown codec | Golden files, body round-trip, header/body offset, порядок полей, restricted YAML 1.2 |
| JSON Schema | Draft 2020-12, package resources, все Node kinds, config, enums и negative cases |
| Discovery | Поиск от вложенного пути, границы vault, symlinks, детерминизм |
| Validation | Syntax, structural, referential, semantic и graph diagnostics |
| Storage | Candidate prevalidation, atomic write/rollback, revision conflict, локальность diff, защита путей |
| Load/mutation performance | Cold open читает Node один раз; warm open не декодирует неизменившийся Markdown; body ленив; mutation не сканирует vault; copy-on-write сохраняет старые snapshots |
| Restricted YAML fast path | Читатель и писатель канонического front matter совпадают с PyYAML или отказываются; 2 000 случайных документов, включая строки на границе переноса |
| Persistent index | Zero-decode reuse, one-file invalidation, checksum/version rebuild, `validate --full` обходит кеш и даёт те же diagnostics |
| Инкрементальные gates | Повторный `format --check` не читает Markdown, но видит переставший быть каноническим файл; чтение одного Node по индексу, включая alias, префикс, неоднозначность, правку извне и отсутствие кеша |
| Formatting | Read-only check, canonical front matter, byte-exact body, idempotence, rollback, concurrent edits |
| Python API | Init/open, atomic metadata/body mutations, operation diagnostics, snapshots |
| CLI | Human/JSON warnings, stderr progress, таблицы/графы, HTML render, `$EDITOR`, body update, initial relations, stdin и exit codes |
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

Актуальное число сценариев и branch coverage фиксируются результатом CI, а не
дублируются вручную в этом документе. Обязательный branch coverage — 70%. CLI
contract tests запускают отдельный процесс и поэтому не входят в coverage
родительского процесса. Дополнительно проходят strict mypy, Ruff, Ruff format
check, `compileall`, сборка пакета и smoke-test установленного `rf` entrypoint.
