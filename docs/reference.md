# Справочник Research Framework

Этот документ перечисляет реализованные возможности версии `0.1.0`. Практика
ручной работы вынесена в [workflow.md](workflow.md), точные JSON-контракты — в
[automation.md](automation.md), обоснование решений — в
[architecture.md](architecture.md).

## 1. Назначение и модель хранения

Research Framework ведёт исследование как типизированный граф обычных файлов:

- каждый Node — отдельный Markdown-файл;
- YAML front matter — структурированные метаданные;
- Markdown body — свободный текст для человека;
- исходящие relations находятся в source-файле;
- входящие связи и индексы вычисляются при загрузке;
- Git хранит историю, ветки и merge conflicts;
- постоянной БД, обязательного кеша и скрытого canonical state нет.

JSON не заменяет файлы. Он используется для CLI automation, экспорта графа и
JSON Schema. YAML ограничен JSON-совместимыми значениями.

## 2. Установка

Требуется Python 3.11 или новее.

CLI как отдельный локальный инструмент:

```bash
uv tool install --editable /path/to/research-framework
rf --help
```

Python API как зависимость другого uv-проекта:

```bash
cd /path/to/application
uv add --editable /path/to/research-framework
```

Разработка самого фреймворка:

```bash
uv sync
uv run pytest
```

## 3. Проект и discovery

Новый автономный проект:

```bash
rf init ./study --title "Context study" --default-language ru
```

В существующем непустом репозитории нужен вложенный каталог:

```bash
cd /path/to/existing-repository
rf init research-graph --title "Исследование проекта"
cd research-graph
```

`rf init` намеренно не записывает в непустую директорию. Остальные CLI-команды
ищут `research.yaml` от текущего каталога к его предкам. Глобального флага
`--project` в текущей версии нет.

Структура проекта:

```text
research-graph/
├── research.yaml
└── research/
    ├── PROJECT.md
    ├── questions/
    ├── hypotheses/
    ├── claims/
    ├── experiments/
    ├── runs/
    ├── evidence/
    ├── assessments/
    ├── sources/
    ├── artifacts/
    └── decisions/
```

`PROJECT.md` предназначен для обзора человеком и не считается Node.

`research.yaml` содержит:

| Поле | Значение |
|---|---|
| `format_version` | версия файлового контракта, сейчас только `1` |
| `project_id` | `prj-` + ULID |
| `title` | название исследования |
| `vault` | относительный путь к каталогу Node-файлов |
| `default_language` | язык проекта |
| `policies` | переключатели семантической валидации |

## 4. Общие свойства Node

Каждый Node имеет:

| Поле | Назначение |
|---|---|
| `format_version` | версия формата файла |
| `id` | typed prefix + ULID |
| `kind` | тип Node |
| `title` | человекочитаемый заголовок |
| `status` | lifecycle: `draft`, `active`, `closed`, `archived` |
| `summary` | короткое необязательное описание |
| `tags` | набор тегов |
| `aliases` | альтернативные уникальные ссылки |
| `created_at/by` | автор и время создания |
| `updated_at/by` | автор и время последней мутации |
| `relations` | исходящие типизированные связи |
| `extensions` | namespace для расширений |
| Markdown body | свободный текст вне front matter |

Node разрешается по полному ID, alias или однозначному префиксу ID. Slug в
имени файла нужен только человеку и не является идентификатором. Он сохраняет
Unicode-буквы и цифры после NFKC normalization, поэтому русские и другие
не-ASCII titles остаются читаемыми в каталоге.

Физического удаления Node нет: `rf node archive` меняет status и сохраняет
историю. Эпистемический вывод хранится в Assessment, а не в lifecycle status.

## 5. Типы Node

| Kind / prefix | Обязательные специальные поля | Необязательные поля |
|---|---|---|
| `question` / `que-` | `question` | `scope` |
| `hypothesis` / `hyp-` | `statement`, `falsification_criteria` | `assumptions` |
| `claim` / `clm-` | `statement` | — |
| `experiment` / `exp-` | `objective`, `method`, `success_criteria`, `protocol_version` | — |
| `run` / `run-` | `started_at`, `outcome` | `finished_at`, `environment` |
| `evidence` / `evd-` | `observation`, `evidence_kind` | `collected_at` |
| `assessment` / `asm-` | `verdict`, `confidence`, `review_state` | `limitations` |
| `source` / `src-` | `source_kind`, `locator` | `citation`, `accessed_at` |
| `artifact` / `art-` | `locator` | `media_type`, `sha256`, `size` |
| `decision` / `dec-` | `outcome`, `rationale` | — |

Допустимые значения:

- Run outcome: `running`, `completed`, `failed`, `cancelled`;
- Evidence kind: `quantitative`, `qualitative`, `citation`, `derived`, `other`;
- Assessment verdict: `supported`, `challenged`, `refuted`, `inconclusive`;
- confidence: `low`, `medium`, `high`;
- review state: `proposed`, `approved`, `rejected`;
- Source kind: `paper`, `book`, `dataset`, `web`, `interview`, `other`.

Завершённый, упавший или отменённый Run требует `finished_at`. Все timestamps
содержат timezone. `accessed_at` Source имеет формат `YYYY-MM-DD`.

## 6. Actors

Audit-поля и мутации используют Actor:

```json
{"kind": "human", "id": "fedor"}
```

```json
{
  "kind": "agent",
  "id": "benchmark-agent",
  "run_id": "agent-run-42",
  "model": "model-name"
}
```

`run_id` и `model` относятся только к agent actor. CLI-флаг `--actor` создаёт
human actor; JSON и Python API позволяют явно создать agent actor.

## 7. Relations

Связь направлена от source к target и хранится только в source-файле.

| Relation | Source | Target |
|---|---|---|
| `addresses` | hypothesis, claim | question |
| `decomposes` | question или hypothesis | тот же kind |
| `depends_on` | hypothesis, claim, experiment | hypothesis, claim |
| `tests` | experiment | hypothesis, claim |
| `instance_of` | run | experiment |
| `produces` | run | evidence, artifact |
| `derived_from` | evidence, claim | run, source, artifact, evidence |
| `supports` | evidence | hypothesis, claim |
| `challenges` | evidence | hypothesis, claim |
| `contradicts` | hypothesis, claim | hypothesis, claim |
| `assesses` | assessment | hypothesis, claim |
| `based_on` | assessment, decision | evidence, assessment, claim |
| `supersedes` | любой Node | тот же kind |
| `related_to` | любой Node | любой Node |

Самоссылки запрещены, кроме `related_to`. ID relation имеет префикс `rel-`.
Backlinks не записываются: `incoming()` вычисляется из исходящих relations.

В `research.yaml` доступны policies:

- `require_falsification_criteria` (в format v1 поле одновременно является
  structural requirement для Hypothesis);
- `require_evidence_provenance` — требовать `derived_from` у Evidence;
- `forbid_dependency_cycles` — запрещать cycles из `depends_on`.

Независимо от policies Run требует ровно один `instance_of`, а Assessment —
`assesses` и `based_on` согласно семантическим правилам.

## 8. CLI

### Проект и проверки

| Команда | Возможность |
|---|---|
| `rf init [PATH] --title TITLE` | создать проект |
| `rf validate [--json]` | проверить весь граф без записи |
| `rf format --check [--json]` | проверить canonical front matter без записи |
| `rf format [--json]` | канонизировать YAML, сохранив body |

### Nodes

| Команда | Возможность |
|---|---|
| `rf node create KIND ...` | создать Node |
| `rf node show REF [--json]` | показать Node, body и revision |
| `rf node list [--kind K] [--status S] [--tag T]` | фильтровать Nodes |
| `rf node update REF --from-json FILE` | изменить разрешённые поля с revision |
| `rf node archive REF --expected-revision REV --actor ID` | архивировать Node |

Общие create-флаги: `--title`, `--summary`, повторяемые `--tag` и `--alias`,
`--actor`, а также взаимоисключающие `--body`, `--body-file`, `--edit`.

Human CLI предоставляет основные специальные поля каждого kind. Все поля,
включая `assumptions`, `environment`, `limitations`, checksums и dates,
доступны через строгий JSON-ввод или Python API.

При создании доступны atomic initial relation flags: `--instance-of`,
повторяемые `--derived-from`, `--assesses`, `--based-on`. Любую другую связь
можно добавить после создания.

### Relations и граф

| Команда | Возможность |
|---|---|
| `rf link add SOURCE KIND TARGET` | добавить исходящую связь |
| `rf link list REF --direction incoming\|outgoing\|both` | показать связи |
| `rf link remove EDGE_ID` | удалить связь из source-файла |
| `rf graph show REF` | показать направленную окрестность |
| `rf graph traverse REF --depth N --direction ...` | BFS traversal |
| `rf graph path SOURCE TARGET` | кратчайший направленный путь |
| `rf graph export --format json` | детерминированно экспортировать граф |
| `rf graph render [--output FILE]` | автономная интерактивная HTML-визуализация |

Human output использует карточки, таблицы и стрелки. `--json` переключает
команду на машинный envelope; `graph export` возвращает raw graph JSON.

### `graph render`

```bash
rf graph render [--output research-graph.html] [--json]
rf graph render --focus REF [--depth N] [--output FILE] [--json]
```

Без `--focus` в HTML попадает полный граф. При `--focus` строится induced
окрестность во входящем и исходящем направлениях; начальный Node всегда включён.
Глубина по умолчанию равна `2`, `0` оставляет только focus Node. `--depth` без
`--focus` и отрицательная глубина являются ошибками аргументов.

Относительный output считается от каталога с `research.yaml`, не от текущей
директории. Родительские директории создаются автоматически. Output обязан
иметь расширение `.html` и находиться вне configured vault; существующий HTML
атомарно заменяется. Документ deterministic для одного GraphSnapshot и набора
аргументов, не загружает CDN assets и не требует сервера. Пользовательский текст
встраивается как escaped JSON и выводится через DOM text nodes.

Human-mode сообщает абсолютный путь и число Node/relations. `--json` возвращает:

```json
{
  "ok": true,
  "data": {
    "output": "/project/reports/graph.html",
    "nodes": 42,
    "edges": 57,
    "focus": null,
    "depth": null
  },
  "warnings": []
}
```

HTML является read-only snapshot. Фильтрация, pan/zoom и сохранение раскладки в
browser `localStorage` не изменяют проект.

Tag picker строится из тегов попавших в текущий full/local GraphView. Пустой
выбор не ограничивает Node. Для нескольких выбранных тегов `any` оставляет Node,
чьи теги пересекаются с выбранным набором, а `all` требует наличия каждого тега.
Tag, kind, status и текстовый фильтры комбинируются одновременно; после
фильтрации показываются только relations, у которых видимы оба конца.

Visibility и selection независимы: фильтр скрывает Node и её рёбра только на
Canvas, но не запрещает чтение карточки. Список relations в карточке содержит
все связи Node внутри текущего GraphView. Переход по relation открывает карточку
скрытого соседа; `(hidden)` и пояснение в карточке показывают, что сосед не
прошёл текущие фильтры. Ограничение `--focus/--depth` действует раньше, при
построении GraphView, поэтому Node за пределами локального snapshot недоступны.

## 9. GraphSnapshot и чтение

`Project.snapshot()` возвращает неизменяемый снимок. После мутации старый
snapshot остаётся прежним, а Project публикует новый.

GraphSnapshot поддерживает:

- `get_node(reference)` и `get_edge(edge_id)`;
- `list_nodes(kind=..., status=..., tags=...)`;
- `outgoing()`, `incoming()`, `neighbors()`;
- BFS `traverse(depth=..., direction=..., kinds=...)`;
- directed `find_path(..., kinds=..., max_depth=...)`;
- детерминированный `export_json()`.

`related_to` и `contradicts` учитываются как симметричные при вычислении
neighbors. Поиск path следует хранимому направлению рёбер.

## 10. Validation и diagnostics

Валидация включает:

1. Syntax: UTF-8, Markdown front matter, restricted YAML.
2. Structural: обязательные поля, типы, enum, IDs, timestamps.
3. Referential: существование target, уникальность ID и aliases.
4. Semantic/graph: relation matrix, обязательные связи, циклы, time ordering.

Diagnostic содержит severity, code, message, path, node/edge ID, field,
suggestion и details. Errors делают операцию неуспешной. Warnings возвращаются
при exit code `0`: в stderr human-mode или в массиве `warnings` JSON-envelope.

## 11. Мутации, revisions и атомарность

Перед create/update/add/remove строится candidate source. Он проходит
structural validation и проверяется против индексов уже валидного snapshot;
cycle detection обходит только достижимую затронутую ветку. Полный vault при
каждой мутации не перечитывается. При ошибке файл не изменяется.

Revision — SHA-256 исходных байтов Node-файла, вычисляемый при чтении и не
записываемый во front matter. Update и archive требуют expected revision. При
внешнем изменении возникает `RevisionConflict`, поэтому чужая правка не
перезаписывается.

Записи выполняются через временный файл, `fsync` и atomic replace. Новый
immutable snapshot публикуется из только что сериализованных bytes. Ранее
выданный snapshot остаётся прежним благодаря copy-on-write; без выдачи
промежуточного snapshot серия мутаций обновляет индексы на месте. При поздней
ошибке публикации выполненная мутация откатывается. `format` готовит все
кандидаты до записи и откатывает уже изменённые файлы при сбое.

Экземпляр `Project` представляет одну in-memory session и намеренно не опрашивает
весь vault перед каждой операцией. После ручных правок или изменений другим
процессом откройте проект заново через `Project.open()`. Revision check всё равно
не позволяет перезаписать внешнее изменение самого source-файла.

## 12. Форматирование и ручное редактирование

Node-файлы можно редактировать обычным текстовым редактором. После ручной
правки выполните:

```bash
rf validate
rf format --check
```

`rf format` меняет только YAML front matter. Markdown body и `PROJECT.md`
сохраняются byte-for-byte. Повторное форматирование идемпотентно.

Restricted YAML запрещает custom tags, anchors, aliases, merge keys, сложные и
дублирующиеся keys, YAML sets, не-JSON значения и неявные YAML 1.1 booleans.

## 13. Git workflow

Фреймворк сам не запускает Git. Типичная операция изменяет один source-файл:

- create добавляет один Node-файл;
- update/archive меняют один Node-файл;
- add/remove relation меняют только source;
- backlinks и отчёты автоматически не записываются.

Перед commit:

```bash
rf validate
rf format --check
git diff --check
git diff
```

Conflict markers не разрешаются автоматически. Сначала разрешите Git conflict,
затем снова запустите validation.

## 14. Python API

```python
from pathlib import Path

from research_framework import Actor, Project, QuestionDraft

project = Project.open(Path("research-graph"))
question = project.create_node(
    QuestionDraft(
        title="Does the change help?",
        question="Does the change improve recall?",
        tags=frozenset({"retrieval"}),
    ),
    actor=Actor.human("fedor"),
)
```

Основные методы Project:

- `init()` и `open()`;
- `snapshot()`, `validate()`, `last_diagnostics()`;
- `create_node(..., initial_relations=...)`;
- `update_node(..., expected_revision=...)`;
- `archive_node(...)`;
- `add_edge()` и `remove_edge()`;
- `format(check=True/False)`.

Публичные draft-классы соответствуют десяти Node kinds. `RelationDraft`
создаёт исходящую initial relation. Actors создаются через `Actor.human()` и
`Actor.agent()`.

Иерархия ошибок:

```text
ResearchFrameworkError
├── ProjectNotFound
├── NodeNotFound
├── EdgeNotFound
├── AmbiguousReference
├── ValidationFailed
├── RevisionConflict
├── UnsupportedFormatVersion
└── StorageError
```

Все исключения имеют стабильный `code`; структурированные детали находятся в
`details`.

## 15. JSON Schema

Schema ресурсов доступны без runtime-зависимости от JSON Schema validator:

```python
from research_framework import node_schema, project_schema

node_contract = node_schema()
project_contract = project_schema()
```

Они описывают сохранённый front matter и project manifest. Межфайловые и
graph-правила проверяет `rf validate`, а не JSON Schema.

## 16. Границы текущей версии

В MVP отсутствуют:

- физическое удаление Node;
- автоматические commit/pull/push и разрешение конфликтов;
- миграции между format versions;
- постоянная БД, полнотекстовый индекс и web UI;
- глобальный CLI-флаг выбора project root;
- инициализация непосредственно в непустой директории.

Project открывается полным сканированием vault. Это предсказуемо и достаточно
для MVP. Обычные мутации повторно vault не сканируют; производный удаляемый
индекс может быть добавлен позднее для ускорения открытия.
