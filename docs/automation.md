# Автоматизация: контракт для агентов, скриптов и CI

Этот документ — нормативная памятка по машинному интерфейсу Research
Framework `0.1.0`. Обзор предметной модели находится в
[reference.md](reference.md), сценарий ручной работы — в
[workflow.md](workflow.md).

## 1. Какой формат где используется

| Задача | Формат |
|---|---|
| Canonical state проекта | Markdown-файлы с restricted YAML front matter |
| Ввод и вывод CLI для автоматизации | JSON |
| Полный снимок графа | JSON |
| Проверка файлового формата внешним инструментом | JSON Schema Draft 2020-12 |
| Вызов из Python | типизированные dataclass и `Project` API |

Не записывайте JSON-файлы в vault как источник истины. JSON нужен только на
границе процесса: передать команду без prompts, однозначно разобрать результат
или экспортировать снимок. После успешной мутации canonical state остаётся в
Markdown/YAML и может быть закоммичен в Git.

## 2. Правила надёжного вызова

1. Запускайте `rf` из project root или его вложенного каталога. Команда ищет
   ближайший `research.yaml` вверх по дереву.
2. Для читающих команд добавляйте `--json`.
3. Для `node create`, `node update` и JSON-варианта `link add` передавайте
   `--from-json FILE`; `-` означает stdin.
4. Разбирайте exit code до интерпретации результата.
5. В JSON-mode stdout содержит ровно один JSON document. Не смешивайте его с
   human-mode.
6. Для update сначала прочитайте свежий `revision` через `node show --json`.
7. После серии изменений выполните `rf validate --json` и
   `rf format --check --json`.

Progress bar намеренно отключён в `--json` и для raw `graph export`: stdout и
stderr остаются пригодными для строгого разбора. Если автоматизация запускает
human-mode и ей нужен heartbeat в логах, используйте корневой флаг
`rf --progress COMMAND ...`.

Инициализация не использует JSON input, но поддерживает JSON output:

```bash
rf init research-graph \
  --title "Automated study" \
  --default-language ru \
  --json
```

Успешный `data.root` содержит абсолютный project root. Целевая директория
должна отсутствовать или быть пустой; команда не встраивает файлы прямо в
непустой repository root.

Пример безопасного shell-вызова:

```bash
rf node create claim --from-json request.json --json >response.json
status=$?
if [ "$status" -ne 0 ]; then
  jq '.error' response.json >&2
  exit "$status"
fi
jq -r '.data.id' response.json
```

## 3. Строгость входа

JSON-запросы являются закрытыми контрактами:

- неизвестные поля запрещены на верхнем уровне, в `actor` и в
  `initial_relations`;
- обязательные поля должны присутствовать;
- строки не преобразуются из чисел, boolean или `null`;
- массив строк должен быть JSON array, а не одна строка;
- `environment` должен быть object;
- `protocol_version` — integer без boolean либо непустая string;
- `size` — integer без boolean;
- необязательное значение следует опустить; `null` не заменяет строку или
  массив;
- ошибка формы запроса возвращает `invalid_arguments`, exit `2` и не изменяет
  файлы.

После проверки envelope запрос проходит те же structural, referential,
semantic и graph rules, что ручная правка. Такая ошибка возвращает exit `3`,
также без частично записанного результата.

## 4. Actor

Human actor:

```json
{"kind": "human", "id": "fedor"}
```

Для human разрешены только `kind` и `id`.

Agent actor:

```json
{
  "kind": "agent",
  "id": "literature-reviewer",
  "run_id": "agent-run-42",
  "model": "model-name"
}
```

Для agent обязательны `kind` и `id`; `run_id` и `model` необязательны. Все
указанные значения — непустые строки. Actor попадает в audit fields
`created_by`/`updated_by` или `created_by` relation.

## 5. Создание Node

Команда:

```bash
rf node create KIND --from-json FILE --json
rf node create KIND --from-json - --json <request.json
```

Общий create envelope:

```json
{
  "title": "Короткий заголовок",
  "summary": "Необязательное резюме",
  "tags": ["retrieval", "benchmark"],
  "aliases": ["H-main"],
  "body": "# Свободный Markdown\n",
  "actor": {"kind": "agent", "id": "planner", "run_id": "run-42"},
  "initial_relations": [
    {
      "kind": "addresses",
      "target": "Q-main",
      "rationale": "Проверяет главный вопрос."
    }
  ]
}
```

`title` и `actor` обязательны. `summary`, `tags`, `aliases`, `body` и
`initial_relations` необязательны. Пустой `initial_relations` — `[]`. `target`
может быть полным ID, alias или однозначным префиксом; в файл записывается
полный ID. Начальные связи валидируются и создаются атомарно вместе с Node.

Добавьте поля выбранного `KIND`:

| KIND | Обязательные поля | Необязательные поля и значения |
|---|---|---|
| `question` | `question` | `scope` |
| `hypothesis` | `statement`, `falsification_criteria` | `assumptions`: array[string] |
| `claim` | `statement` | — |
| `experiment` | `objective`, `method`, `success_criteria`, `protocol_version` | — |
| `run` | `started_at`, `outcome` | `finished_at`, `environment`: object |
| `evidence` | `observation`, `evidence_kind` | `collected_at` |
| `assessment` | `verdict`, `confidence`, `review_state` | `limitations`: array[string] |
| `source` | `source_kind`, `locator` | `citation`, `accessed_at` |
| `artifact` | `locator` | `media_type`, `sha256`, `size` |
| `decision` | `outcome`, `rationale` | — |

Enum и форматные ограничения:

- `run.outcome`: `running`, `completed`, `failed`, `cancelled`;
- `evidence_kind`: `quantitative`, `qualitative`, `citation`, `derived`,
  `other`;
- `verdict`: `supported`, `challenged`, `refuted`, `inconclusive`;
- `confidence`: `low`, `medium`, `high`;
- `review_state`: `proposed`, `approved`, `rejected`;
- `source_kind`: `paper`, `book`, `dataset`, `web`, `interview`, `other`;
- timestamps — ISO 8601 с timezone; `accessed_at` — `YYYY-MM-DD`;
- `sha256` — 64 hexadecimal characters; `size >= 0`.

Пример Run с обязательной связью:

```json
{
  "title": "Benchmark 32k",
  "started_at": "2026-08-18T10:00:00+07:00",
  "outcome": "running",
  "environment": {"dataset": "v3", "seed": 42},
  "actor": {"kind": "agent", "id": "runner", "run_id": "bench-42"},
  "initial_relations": [
    {"kind": "instance_of", "target": "exp-01K2M7K6R9JAFWQ3NRM8V4C1TX"}
  ]
}
```

## 6. Чтение Nodes

```bash
rf node show REF --json
rf node list --kind hypothesis --status active --tag retrieval --json
```

`show` возвращает все поля Node, Markdown `body` и вычисленный `revision`.
`list` возвращает array компактных Nodes без `body` и `revision`. Несколько
`--tag` означают, что Node должен содержать все заданные теги.

REF разрешается в порядке: полный ID, точный alias, однозначный ID prefix.
Неоднозначность никогда не разрешается эвристически.

## 7. Обновление Node

```bash
rf node update REF --from-json update.json --json
```

Точный envelope:

```json
{
  "patch": {
    "summary": "Проверено повторным запуском",
    "tags": ["retrieval", "verified"],
    "status": "active"
  },
  "expected_revision": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "actor": {"kind": "agent", "id": "reviewer", "run_id": "review-7"}
}
```

Разрешены изменяемые metadata-поля уже существующего Node, а также
`summary`, `tags`, `aliases`, `extensions`. Запрещены `format_version`, `id`,
`kind`, `created_at`, `created_by` и `relations`. Body через `node update` не
изменяется. Status: `draft`, `active`, `closed`, `archived`.

`expected_revision` — SHA-256 исходных байтов Node-файла из последнего
`node show`. При несовпадении команда возвращает exit `5` и актуальный файл не
перезаписывает. После успешного update используйте новый `data.revision`.

Архивирование — специализированный update status:

```bash
rf node archive REF \
  --expected-revision REVISION \
  --actor automation \
  --json
```

Оно сохраняет файл и историю, но устанавливает `status: archived`. У archive
пока нет JSON actor input: `--actor` создаёт human actor.

## 8. Relations

Добавление:

```bash
rf link add --from-json - --json <<'JSON'
{
  "source": "evd-01K2M7M4",
  "kind": "supports",
  "target": "H-main",
  "rationale": "Recall вырос на 13%.",
  "actor": {"kind": "agent", "id": "reviewer", "run_id": "review-7"}
}
JSON
```

Поля `source`, `kind`, `target`, `actor` обязательны; `rationale` необязателен.
Точная relation matrix приведена в [reference.md](reference.md#7-relations).
Операция меняет только source-файл.

Чтение и удаление:

```bash
rf link list REF --direction both --json
rf link remove RELATION_ID --actor automation --json
```

`direction`: `incoming`, `outgoing` или `both`. У `link remove` пока нет
JSON actor input: флаг `--actor` записывает human actor. Удаляется relation, а
не target Node.

## 9. Запросы к графу

```bash
rf graph show REF --json
rf graph traverse REF --direction both --depth 2 --json
rf graph path SOURCE TARGET --json
rf graph export --format json
rf graph render --output reports/graph.html --json
```

- `show`: center и все смежные edges;
- `traverse`: BFS и array достигнутых Nodes без starting Node;
- `path`: кратчайший направленный путь как array edges; пустой array означает
  «путь не найден» или source равен target;
- `export`: детерминированный полный снимок `{ "nodes": [...], "edges": [...] }`.
- `render`: записывает standalone HTML и возвращает output path, число nodes и
  edges, resolved focus ID и depth в обычном success envelope.

`graph export` — исключение: это raw JSON без `ok/data/warnings`, потому что
его результат и есть переносимый граф.

Для ограниченного артефакта используйте
`--focus REF --depth N`. При `--focus` без `--depth` применяется глубина `2`;
`--depth` без focus отклоняется. Относительный `--output` разрешается от project
root, обязан заканчиваться на `.html` и не может находиться внутри vault.
Команда только читает GraphSnapshot и атомарно записывает производный файл;
исследовательские Markdown-документы не меняются.

Сгенерированный HTML открывается в `independent` mode. Пользователь может
переключить его в `linked context`, выбрать Anchor kinds (default:
`hypothesis`, `claim`) и управлять unlinked Context. Это browser-only state: оно
не меняет JSON response `graph render`, embedded GraphView или файлы проекта.

## 10. Validation и formatting в CI

```bash
rf validate --json >validation.json
rf format --check --json >formatting.json
```

Validation success может содержать warnings при exit `0`:

```json
{
  "ok": true,
  "data": {"diagnostics": []},
  "warnings": [
    {
      "severity": "warning",
      "code": "archived_target",
      "message": "relation targets an archived node"
    }
  ]
}
```

Не игнорируйте `warnings`: они не останавливают мутацию, но должны попасть в
лог агента или review. Validation errors дают exit `3` и находятся в
`error.details.diagnostics`.

`format --check` ничего не записывает. Drift даёт exit `1`, code
`formatting_required` и `details.paths`. `rf format --json` применяет canonical
YAML formatting, сохраняет Markdown body byte-for-byte и сообщает
`changed_files`.

Минимальный CI gate:

```bash
rf validate --json
rf format --check --json
git diff --check
```

## 11. Response envelope

Обычный успех:

```json
{
  "ok": true,
  "data": {},
  "warnings": []
}
```

Ошибка:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_arguments",
    "message": "title must be a string",
    "details": {}
  }
}
```

Поля error code и details стабильнее текста message; автоматизация должна
ветвиться по exit code и `error.code`, а message показывать человеку.

## 12. Exit codes

| Code | Значение | Типичная реакция агента |
|---:|---|---|
| `0` | успех, возможно warnings | обработать `data`, записать warnings в лог |
| `1` | formatting drift или внутренняя framework/storage error | исправить format либо остановиться с диагностикой |
| `2` | неверные CLI args или строгий JSON contract | исправить запрос; повтор без reread допустим |
| `3` | validation failed | исправить graph/metadata по diagnostics |
| `4` | project/node/edge не найден либо reference неоднозначен | уточнить reference или cwd |
| `5` | revision conflict | перечитать Node, объединить изменения, повторить |
| `6` | неподдерживаемая format version | не записывать; обновить framework/мигрировать проект |

## 13. Идемпотентность и повтор команд

Create и link add не имеют idempotency key: слепой повтор после неизвестного
результата может создать дубликат. Сначала перечитайте graph и проверьте,
прошла ли операция. Update защищён revision, но повтор уже успешного update со
старой revision вернёт conflict. `validate`, `format --check` и чтение безопасно
повторять; применяющий `format` идемпотентен.

CLI не выполняет `git add`, commit, pull или push. Решение о публикации
изменений остаётся у вызывающего процесса.

## 14. Python API вместо subprocess

Если автоматизация написана на Python, можно не сериализовать команды:

```python
import sys
from pathlib import Path

from research_framework import (
    Actor,
    EdgeKind,
    ProgressEvent,
    Project,
    RelationDraft,
    RunDraft,
)

def progress(event: ProgressEvent) -> None:
    print(event.phase, event.current, event.total, file=sys.stderr)


project = Project.open(Path("research-graph"), progress=progress)
run = project.create_node(
    RunDraft(
        title="Benchmark 32k",
        started_at="2026-08-18T10:00:00+07:00",
        outcome="running",
        environment={"seed": 42},
    ),
    actor=Actor.agent("runner", run_id="bench-42"),
    initial_relations=(
        RelationDraft(EdgeKind.INSTANCE_OF, "exp-01K2M7K6R9JAFWQ3NRM8V4C1TX"),
    ),
)
print(run.id, run.revision)
```

Callback получает события `discovering`, `loading`, `validating` и `indexing`;
`Project.format(progress=...)` дополнительно сообщает `formatting`. Это позволяет
агенту отличить долгую обработку от зависания без разбора human progress bar.

`Project.snapshot()` возвращает immutable `GraphSnapshot`; после мутации
возьмите новый snapshot. Перехватывайте подклассы `ResearchFrameworkError` и
используйте их `code`/`details`.

## 15. JSON Schema

Файловый контракт можно получить из установленного пакета:

```python
from research_framework import node_schema, project_schema

node_contract = node_schema()
project_contract = project_schema()
```

Schema проверяет `research.yaml` и YAML front matter после представления как
JSON-совместимый object. Она не заменяет `rf validate`: existence targets,
alias uniqueness, relation matrix, required graph edges и cycles требуют
контекста всего проекта.
