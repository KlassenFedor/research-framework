# Пользовательский workflow

Это практический сценарий работы с Research Framework: от создания проекта до
проверки Git diff. Все команды изменяют только файлы проекта; `rf` никогда не
делает `git add`, `commit`, `pull` или `push` самостоятельно.

Полный перечень полей, relations и команд находится в
[reference.md](reference.md). Строгий контракт для агентов и CI — в
[automation.md](automation.md).

## 0. Установка и выбор расположения

Требуется Python 3.11+. Установить CLI из локального checkout удобно через
`uv`:

```bash
uv tool install --editable /path/to/research-framework
rf --help
```

После изменений исходного checkout editable-установка видит новый код. Для
обычной не-editable установки уберите `--editable`.

Research root можно держать отдельным репозиторием либо вложить в существующий.
`rf init` не пишет в непустой каталог, поэтому для существующего проекта
создайте дочернюю директорию и затем работайте из неё:

```bash
cd /path/to/existing-project
rf init research-graph --title "Исследование проекта" --default-language ru
cd research-graph
```

Команды ищут ближайший `research.yaml` от текущего каталога вверх. Из
родительского каталога существующего проекта они вложенный research root не
найдут; глобального `--project` в версии `0.1.0` нет.

## 1. Создание проекта

```bash
rf init ./context-study --title "Исследование длины контекста" \
  --default-language ru
cd context-study
git init
git add research.yaml research/
git commit -m "Initialize research project"
```

`research.yaml` определяет корень и vault проекта. Каждый узел хранится в
отдельном Markdown-файле: YAML front matter содержит структурированные данные,
а остальная часть файла — свободный Markdown body.

## 2. Создание узлов человеком

Обязательные поля конкретного типа передаются флагами. Body можно передать
строкой, прочитать из файла или явно открыть в `$EDITOR`:

```bash
rf node create question \
  --title "Влияет ли контекст на recall?" \
  --question "Повышает ли окно 32k recall относительно 8k?" \
  --scope "Фиксированные модель, датасет и retrieval pipeline" \
  --body-file notes/question.md \
  --tag retrieval \
  --actor fedor

export EDITOR="code --wait"  # либо vim, nano и т. п.
rf node create hypothesis \
  --title "Длинный контекст повышает recall" \
  --statement "Окно 32k повышает recall минимум на 10%." \
  --falsification-criteria "Медианный рост меньше 10%." \
  --actor fedor \
  --edit
```

`--body`, `--body-file` и `--edit` взаимоисключающие. `--edit` не запускается
неявно: если переменная `EDITOR` отсутствует или редактор завершился с ошибкой,
команда возвращает exit code `2` и не создаёт узел. В JSON-mode `--edit`
запрещён, чтобы внешний процесс не нарушил машинно-читаемый stdout; body следует
передавать полем JSON или через `--body-file` в human-oriented вызове.

Узлы с обязательной исходящей связью можно создать атомарно. Например, Run
должен сразу ссылаться на Experiment:

```bash
rf node create run \
  --title "Benchmark 32k" \
  --started-at "2026-08-17T12:00:00+07:00" \
  --outcome running \
  --instance-of exp-01K2M7K6R9JAFWQ3NRM8V4C1TX \
  --actor fedor
```

### Как выглядит полный исследовательский цикл

Фреймворк не навязывает порядок работы, но типичный граф развивается так:

```text
Question ← addresses — Hypothesis ← tests — Experiment ← instance_of — Run
                              ↑                                  │
                         supports                           produces
                              │                                  ↓
                         Evidence — derived_from → Run/Source/Artifact

Hypothesis/Claim ← assesses — Assessment — based_on → Evidence/Claim
                          Decision — based_on → Evidence/Assessment/Claim
```

Практический порядок:

1. `question` фиксирует проверяемый вопрос и scope.
2. `hypothesis` или `claim` формулирует утверждение; `addresses` связывает его
   с вопросом.
3. `experiment` описывает воспроизводимый protocol и через `tests` указывает,
   что проверяется.
4. `run` фиксирует конкретный запуск и ровно один `instance_of`.
5. `source` и `artifact` регистрируют внешние материалы и результаты.
6. `evidence` записывает наблюдение, `derived_from` — происхождение, а
   `supports`/`challenges` — эпистемическое направление.
7. `assessment` отдельно формулирует verdict, confidence и limitations.
8. `decision` фиксирует практический outcome и через `based_on` указывает
   основания.

Это разделение важно: status Node (`draft`, `active`, `closed`, `archived`) —
состояние работы, а не степень истинности. «Подтверждено» следует хранить в
Assessment.

## 3. Просмотр графа

Human-mode выводит карточки, таблицы и направленные окрестности:

```bash
rf node show hyp-01K2M7K6
rf node list --kind hypothesis --status active --tag retrieval
rf link list hyp-01K2M7K6 --direction both
rf graph show hyp-01K2M7K6
rf graph traverse hyp-01K2M7K6 --direction both --depth 2
rf graph path run-01K2M7M4 hyp-01K2M7K6
```

Полный ID можно сокращать только до однозначного префикса. Alias также можно
использовать вместо ID. Неоднозначная или отсутствующая ссылка не выбирается
эвристически и возвращает exit code `4`.

### Интерактивная HTML-визуализация

Полный граф можно собрать в один автономный файл:

```bash
rf graph render
```

Результат по умолчанию — `research-graph.html` в каталоге рядом с
`research.yaml`. Даже если команда запущена из вложенной директории, output
разрешается относительно корня проекта. Откройте файл в браузере напрямую;
сервер, интернет и установка расширения не нужны.

Для большого графа удобнее отрендерить локальную окрестность. `REF` принимает
полный ID, однозначный префикс или alias:

```bash
rf graph render \
  --focus H-context \
  --depth 2 \
  --output reports/context-neighborhood.html
```

В HTML доступны:

- force-directed layout, pan, zoom и ручное перетаскивание Node;
- поиск по title, ID, tags и aliases;
- фильтры по Node kind, status и relation kind;
- включение и отключение подписей связей;
- карточка выбранного Node с metadata, Markdown body и соседними relations;
- переход к соседу из карточки;
- сохранение ручной раскладки в `localStorage` браузера.

HTML — производный read-only артефакт: он не меняет Markdown-файлы и не является
источником истины. Координаты не попадают в Git. Повторите `rf graph render`
после изменений графа; сохранённые позиции применятся к тому же набору Node.
Запись внутрь canonical vault запрещена, чтобы generated HTML не был принят за
исследовательский документ. Явный output должен иметь расширение `.html`.

## 4. Связи и локальность изменений

Связь хранится только в файле source-узла, поэтому её добавление и удаление
меняет один файл:

```bash
rf link add evd-01K2M7M4 supports hyp-01K2M7K6 \
  --rationale "Recall вырос на 13%." \
  --actor fedor
rf link remove rel-01K2M7N2 --actor fedor
git diff --stat
git diff
```

Backlinks вычисляются при загрузке графа. Файл target-узла при добавлении
отношения не переписывается.

## 5. Обновление и архивирование

Мутации существующего узла используют revision из `node show --json`. Это
защищает ручные правки от тихой перезаписи:

```bash
rf node show hyp-01K2M7K6 --json > shown.json
```

Создайте `update.json` с revision из ответа:

```json
{
  "patch": {
    "summary": "Проверено повторным benchmark"
  },
  "expected_revision": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "actor": {
    "kind": "human",
    "id": "fedor"
  }
}
```

```bash
rf node update hyp-01K2M7K6 --from-json update.json
rf node archive hyp-01K2M7K6 \
  --expected-revision "<revision from the latest node show>" \
  --actor fedor
```

Если файл изменился после чтения revision, команда возвращает exit code `5` и
оставляет внешнюю правку без изменений. Архивирование меняет status, но не
удаляет файл и не обрывает историю Git.

## 6. Автоматизация и агенты

`--json` гарантирует один JSON document в stdout. Полный input мутаций можно
передавать файлом или через stdin:

```bash
rf node create claim --from-json claim.json --json
rf link add --from-json - --json <<'JSON'
{
  "source": "evd-01K2M7M4",
  "kind": "supports",
  "target": "hyp-01K2M7K6",
  "actor": {"kind": "agent", "id": "reviewer", "run_id": "agent-run-42"}
}
JSON
```

Успех имеет поля `ok`, `data`, `warnings`; ошибка — `ok: false` и объект
`error`. В JSON-mode нет prompts и служебного текста в stdout.

## 7. Проверка перед commit

```bash
rf validate
rf format --check
```

`validate` проверяет синтаксис, структуру, ссылки и семантику всего графа.
Errors дают exit code `3`; warnings показываются отдельно и не превращают
успешную операцию в ошибку.

`format --check` ничего не записывает и возвращает `1`, если front matter не
каноничен. Явный `rf format` форматирует только YAML front matter, сохраняет
Markdown body byte-for-byte и идемпотентен.

Рекомендуемый Git-цикл:

```bash
rf validate
rf format --check || rf format
git diff --check
git diff
git add research.yaml research/
git commit -m "Record retrieval experiment"
```

При Git-конфликте сначала вручную разрешите маркеры, затем снова выполните
`rf validate`. Research Framework не пытается автоматически выбирать одну из
конфликтующих научных записей.

## 8. Контракты формата

JSON Schema Draft 2020-12 поставляются вместе с Python-пакетом:

```python
from research_framework import node_schema, project_schema

node_contract = node_schema()
project_contract = project_schema()
```

Schema полезны для редакторов и внешних инструментов. Каноническую проверку
целого проекта выполняет `rf validate`, потому что она дополнительно проверяет
межфайловые ссылки и правила графа.

## 9. Ручное редактирование файлов

Markdown-файлы остаются обычными текстовыми документами. Можно править body и
front matter редактором, но соблюдайте несколько правил:

- не меняйте `id`, `kind`, `created_at`, `created_by` и relation IDs;
- не создавайте backlinks вручную — incoming relations вычисляются;
- используйте только JSON-совместимые YAML values;
- не используйте YAML anchors, aliases, merge keys или custom tags;
- timestamps указывайте с timezone;
- после правки всегда запускайте `rf validate`.

`rf format` канонизирует только front matter. Markdown body и `PROJECT.md`
сохраняются byte-for-byte. Имя файла содержит удобный slug, но ссылкой служит
ID или alias; после изменения title переименование файла не обязательно.
Unicode сохраняется, поэтому title `Тестовый вопрос` получает slug
`тестовый-вопрос`.

## 10. Диагностика проблем

| Симптом | Причина и действие |
|---|---|
| `project_not_found` | Перейдите в research root или его вложенный каталог |
| reference не найден | Проверьте полный ID/alias; отсутствие даёт exit `4` |
| reference ambiguous | Используйте более длинный ID prefix или полный ID |
| revision conflict | Снова выполните `node show --json`, объедините правки |
| validation failed | Исправьте перечисленные diagnostics; файлы мутацией не изменены |
| formatting required | Выполните `rf format`, проверьте diff |
| unsupported format version | Не записывайте проект старой версией CLI |

Коды завершения: `0` — успех, `1` — format drift/framework error, `2` —
аргументы, `3` — validation, `4` — not found/ambiguous, `5` — revision
conflict, `6` — format version. Warnings выводятся в stderr, но сохраняют exit
`0`.

Если команда неожиданно завершилась, сначала выполните:

```bash
pwd
rf validate
git status --short
git diff
```

Мутации атомарны и предварительно валидируются. Однако Git остаётся последней
точкой восстановления и аудита, поэтому просматривайте diff до commit.
