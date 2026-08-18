# Архитектура текстового ядра Research Framework

- Статус: **утверждено для разработки**
- Версия документа: **0.2**
- Целевая версия продукта: **MVP 0.1**

## 1. Назначение документа

Этот документ фиксирует архитектуру первой минимально жизнеспособной версии
Research Framework до начала разработки.

MVP должен позволять:

- хранить исследование как граф объектов и типизированных связей;
- хранить весь проект в обычных текстовых файлах внутри Git-репозитория;
- читать и изменять граф из терминала;
- читать и изменять тот же граф через публичный Python API;
- работать с файлами вручную, в том числе через Obsidian или текстовый редактор;
- проверять целостность графа после ручных и автоматических изменений;
- одинаково хорошо обслуживать человека, Python-код и AI-агента.

Документ намеренно не описывает web UI, сервер синхронизации и автоматическое
проведение исследований. Эти возможности могут быть добавлены поверх ядра после
стабилизации файлового формата и доменной модели.

## 2. Главные архитектурные решения

### 2.1. Файлы являются единственным источником истины

Все исследовательские объекты хранятся в Markdown-файлах с ограниченным YAML
1.2 front matter. Логический контракт метаданных использует только типы,
которые без потерь представимы в JSON; JSON остаётся форматом машинного обмена,
CLI и экспорта.
Для открытия и редактирования проекта не нужны сервер или база данных.

MVP не создаёт обязательную БД. При необходимости в будущем можно добавить
локальный пересобираемый индекс, но его удаление не должно приводить к потере
данных.

### 2.2. Логическая модель является графом, физическая — набором файлов

Граф существует на уровне доменной модели:

- Markdown-файл представляет узел;
- запись в `relations` представляет исходящее ребро;
- входящие рёбра вычисляются при загрузке;
- расположение файла в каталоге помогает человеку, но не определяет его
  идентичность.

Графовая БД для этого не требуется. При открытии проекта ядро строит снимок
графа в памяти.

### 2.3. CLI и Python API используют один application layer

CLI не должен содержать отдельную бизнес-логику. Любая команда терминала
вызывает ту же операцию, которая доступна через Python API.

```text
                          ┌──────────────┐
                          │     CLI      │
                          └──────┬───────┘
                                 │
┌──────────────┐          ┌──────▼───────┐          ┌──────────────┐
│  Python API  ├─────────►│ Application  │◄─────────┤ Будущий MCP  │
└──────────────┘          │   services   │          └──────────────┘
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │ Domain graph │
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │ File storage │
                          │ Markdown/YAML│
                          └──────────────┘
```

Будущий MCP или HTTP API также должен быть адаптером к этому слою, а не новой
реализацией поведения.

### 2.4. Один объект — один файл

Нельзя хранить все гипотезы или связи в одном центральном файле. Файлы должны
быть небольшими и независимо изменяемыми, чтобы Git-конфликты оставались
локальными.

### 2.5. Идентификатор не зависит от имени и пути файла

Каждый объект получает постоянный глобально уникальный ID. Переименование
заголовка или перемещение файла не ломает связи.

Для ID предлагается формат с префиксом типа и ULID:

```text
que-01K2M7J94Y9R1JY8G5C2Q7F8BA
hyp-01K2M7K6R9JAFWQ3NRM8V4C1TX
evd-01K2M7M4CNG7M1R0QP91W6N3JD
```

Последовательные ID вроде `H-001` не используются как первичные: два автора в
разных Git-ветках могут независимо создать одинаковый номер. CLI может
показывать сокращённый ID и поддерживать пользовательские aliases.

## 3. Границы MVP

### 3.1. В MVP входит

- инициализация файлового исследовательского проекта;
- фиксированный набор типов узлов;
- фиксированный набор типов связей;
- загрузка полного графа в память;
- создание, чтение, изменение и архивирование узлов;
- создание, чтение и удаление связей;
- выборка узлов по типу, статусу и тегам;
- просмотр соседей и обход графа на ограниченную глубину;
- поиск пути между двумя узлами;
- структурная и семантическая валидация проекта;
- человекочитаемый и JSON-вывод CLI;
- публичный Python API;
- экспорт снимка графа в JSON;
- автономная read-only HTML-визуализация полного или локального графа;
- тесты файлового формата, доменной модели, CLI и Python API.

### 3.2. В MVP не входит

- обязательная база данных или поисковый индекс;
- динамический write-capable web-интерфейс и сервер;
- Obsidian plugin;
- real-time совместное редактирование;
- управление Git: commit, pull, push и разрешение конфликтов;
- хранение больших бинарных артефактов;
- запуск экспериментального кода;
- полнотекстовый поисковый движок;
- язык сложных графовых запросов;
- автоматическое вычисление истинности и confidence;
- генерация summaries с помощью LLM;
- MCP-сервер и оркестрация AI-агентов;
- пользовательские типы узлов и связей.

Некоторые из этих возможностей учитываются в дизайне, но не реализуются в
первой версии.

## 4. Структура исследовательского проекта

Рекомендуемая структура:

```text
example-project/
├── README.md
├── research.yaml
├── research/
│   ├── PROJECT.md
│   ├── questions/
│   ├── hypotheses/
│   ├── claims/
│   ├── experiments/
│   ├── runs/
│   ├── evidence/
│   ├── assessments/
│   ├── sources/
│   ├── artifacts/
│   └── decisions/
├── artifacts/
├── code/
└── data/
```

Только `research.yaml` и каталог, указанный в нём как `vault`, имеют специальное
значение для ядра. `code`, `data` и внешний `artifacts` являются предлагаемой,
но не обязательной структурой.

Пример конфигурации:

```yaml
format_version: 1
project_id: prj-01K2M7KHDMGD1W95GC8F8Y4RXQ
title: Исследование качества retrieval
vault: research
default_language: ru

policies:
  require_falsification_criteria: true
  require_evidence_provenance: true
  forbid_dependency_cycles: true
```

`PROJECT.md` — обычный обзорный документ для человека. Он не заменяет граф и не
является обязательным реестром всех объектов.

## 5. Доменная модель

### 5.1. Общая модель узла

Каждый узел имеет одинаковую базовую структуру:

| Поле | Тип | Обязательное | Назначение |
|---|---|---:|---|
| `format_version` | integer | да | Версия файлового формата |
| `id` | string | да | Постоянный уникальный ID |
| `kind` | enum | да | Тип узла |
| `title` | string | да | Короткое человекочитаемое имя |
| `status` | enum | да | Состояние жизненного цикла |
| `summary` | string | нет | Краткое содержание без чтения body |
| `tags` | list[string] | нет | Неформальная классификация |
| `aliases` | list[string] | нет | Короткие имена и старые обозначения |
| `created_at` | datetime | да | Время создания с часовым поясом |
| `created_by` | Actor | да | Человек или агент, создавший объект |
| `updated_at` | datetime | да | Время последнего изменения через ядро |
| `updated_by` | Actor | да | Автор последнего изменения через ядро |
| `relations` | list[Relation] | нет | Канонические исходящие связи |
| `extensions` | mapping | нет | Namespaced расширения внешних систем |
| Markdown body | string | нет | Подробное свободное описание |

Общий `status` описывает жизненный цикл документа:

```text
draft -> active -> closed -> archived
```

Он не описывает истинность утверждения. Например, поддержанная гипотеза может
быть `closed`, а её эпистемическая оценка хранится в отдельном `assessment`.

Неизвестные top-level поля считаются ошибкой, чтобы опечатка не превращалась в
молча потерянную метаинформацию. Произвольные данные размещаются в
`extensions.<namespace>`.

### 5.2. Actor и происхождение изменений

```yaml
created_by:
  kind: human
  id: fedor
```

или:

```yaml
created_by:
  kind: agent
  id: literature-reviewer
  run_id: run-2026-08-16-001
  model: optional-model-name
```

Обязательными являются `kind` и `id`. `run_id` позволяет связать изменения с
конкретным запуском агента. Полный prompt в метаданные по умолчанию не пишется:
он может быть большим или содержать чувствительные данные.

### 5.3. Типы узлов MVP

#### `question`

Исследовательский вопрос. Может декомпозироваться на более узкие вопросы.

Специальные поля:

- `question`: точная формулировка вопроса;
- `scope`: необязательные границы рассмотрения.

#### `hypothesis`

Проверяемое предположение.

Специальные поля:

- `statement`: проверяемая формулировка;
- `falsification_criteria`: условия, при которых гипотеза считается
  опровергнутой;
- `assumptions`: необязательный список предпосылок.

#### `claim`

Утверждение, используемое в рассуждениях. Claim может быть теоретическим
выводом, промежуточным заключением или утверждением из источника.

Специальное поле:

- `statement`: точная формулировка утверждения.

Отдельного типа `fact` нет. В рамках фреймворка «текущий факт» — это claim с
одобренным assessment и прослеживаемым evidence. Такая модель не позволяет
незаметно превратить интерпретацию в объективную истину.

#### `experiment`

Версионируемый план проверки гипотезы или claim.

Специальные поля:

- `objective`: цель;
- `method`: краткое описание метода;
- `success_criteria`: критерии результата;
- `protocol_version`: версия протокола.

Подробный протокол может находиться в Markdown body или во внешнем artifact.

#### `run`

Конкретное исполнение experiment.

Специальные поля:

- `started_at`;
- `finished_at`, если запуск завершён;
- `outcome`: `running`, `completed`, `failed`, `cancelled`;
- `environment`: необязательное структурированное описание окружения.

Run связывается ровно с одним experiment через `instance_of`.

#### `evidence`

Зафиксированное наблюдение или результат. Evidence само по себе нейтрально:
поддержка или опровержение утверждения задаётся ребром.

Специальные поля:

- `observation`: краткое описание наблюдения;
- `evidence_kind`: `quantitative`, `qualitative`, `citation`, `derived` или
  `other`;
- `collected_at`, если время отличается от создания записи.

Evidence должно иметь хотя бы одну связь `derived_from` с run, source или
artifact, если политика проекта явно не разрешает отсутствие provenance.

#### `assessment`

Версионированная оценка hypothesis или claim конкретным автором.

Специальные поля:

- `verdict`: `supported`, `challenged`, `refuted` или `inconclusive`;
- `confidence`: `low`, `medium` или `high`;
- `limitations`: необязательный список ограничений;
- `review_state`: `proposed`, `approved` или `rejected`.

Assessment связывается с оцениваемым узлом через `assesses`, а с основаниями —
через `based_on`. Новая оценка не перезаписывает старую, а связывается с ней
через `supersedes`.

#### `source`

Внешний источник: статья, книга, датасет, интервью или веб-страница.

Специальные поля:

- `source_kind`: `paper`, `book`, `dataset`, `web`, `interview` или `other`;
- `locator`: DOI, URL, ISBN или локальный путь;
- `citation`: необязательное библиографическое описание;
- `accessed_at`: необязательная дата доступа.

#### `artifact`

Файл или иной материальный результат исследования.

Специальные поля:

- `locator`: путь или URI;
- `media_type`: необязательный MIME type;
- `sha256`: рекомендуемый hash содержимого;
- `size`: необязательный размер в байтах.

Ядро хранит метаданные и ссылку. Большой файл не обязан находиться в Git.

#### `decision`

Зафиксированное исследовательское решение.

Специальные поля:

- `outcome`: что решено;
- `rationale`: почему принято решение.

Основания задаются связями `based_on`.

### 5.4. Почему assessment является отдельным узлом

Хранение `verdict` непосредственно в hypothesis привело бы к потере важных
данных:

- кто сделал заключение;
- когда оно было сделано;
- какие evidence использовались;
- существовали ли альтернативные оценки;
- какое заключение было пересмотрено.

Отдельный узел делает разногласия и изменение позиции частью графа, а не
аномалией хранения.

## 6. Модель связей

### 6.1. Представление ребра

В файле хранится только исходящая связь:

```yaml
relations:
  - id: rel-01K2M8C58E09VJMMA2XT67F1RQ
    kind: supports
    target: hyp-01K2M7K6R9JAFWQ3NRM8V4C1TX
    rationale: Recall вырос на 13% на заранее зафиксированном наборе.
    created_at: 2026-08-16T12:30:00+07:00
    created_by:
      kind: human
      id: fedor
```

В памяти relation становится полноценным Edge с полями `source` и `target`.
`source` определяется файлом-владельцем, поэтому не дублируется в YAML.

Каждое ребро имеет ID, чтобы его можно было однозначно изменить или удалить,
даже если между двумя узлами существует несколько связей одного типа.

### 6.2. Каноническое направление связей

| Связь | Допустимый source | Допустимый target | Смысл |
|---|---|---|---|
| `addresses` | hypothesis, claim | question | Отвечает на вопрос |
| `decomposes` | question, hypothesis | тот же kind | Декомпозирует объект |
| `depends_on` | hypothesis, claim, experiment | hypothesis, claim | Имеет логическую зависимость |
| `tests` | experiment | hypothesis, claim | Проверяет утверждение |
| `instance_of` | run | experiment | Является запуском протокола |
| `produces` | run | evidence, artifact | Создаёт результат |
| `derived_from` | evidence, claim | run, source, artifact, evidence | Имеет происхождение |
| `supports` | evidence | hypothesis, claim | Поддерживает утверждение |
| `challenges` | evidence | hypothesis, claim | Ослабляет или ставит под сомнение |
| `contradicts` | hypothesis, claim | hypothesis, claim | Логически противоречит |
| `assesses` | assessment | hypothesis, claim | Оценивает утверждение |
| `based_on` | assessment, decision | evidence, assessment, claim | Основано на объекте |
| `supersedes` | любой kind | тот же kind | Заменяет предыдущую версию |
| `related_to` | любой kind | любой kind | Нестрогая вспомогательная связь |

Типы и матрица допустимости фиксированы в MVP. `related_to` нужен как escape
hatch, но валидатор может предупреждать о его чрезмерном использовании.

### 6.3. Обратные и симметричные связи

Обратные связи никогда не записываются автоматически в target-файл. Например,
если experiment содержит `tests -> hypothesis`, команда просмотра hypothesis
вычислит `tested_by` как входящее представление.

Это важно для Git: создание experiment изменяет только его новый файл и не
создаёт конфликт в популярном файле hypothesis.

`contradicts` и `related_to` считаются симметричными при чтении, но физически
записываются один раз.

### 6.4. Ограничения графа

Валидатор проверяет:

- существование source и target;
- соответствие типов матрице;
- уникальность relation ID;
- отсутствие self-link там, где он не имеет смысла;
- отсутствие циклов `depends_on`, если это запрещено политикой;
- отсутствие циклов `decomposes`;
- одинаковый kind для `supersedes`;
- ровно один исходящий `instance_of` у run;
- наличие `assesses` у assessment;
- наличие provenance у evidence.

Связи `supports` и `challenges` не изменяют verdict автоматически. Assessment
остаётся явным решением автора.

## 7. Файловый формат

### 7.1. Имя файла

Рекомендуемый формат:

```text
<id>--<slug>.md
```

Пример:

```text
hyp-01K2M7K6R9JAFWQ3NRM8V4C1TX--longer-context-improves-recall.md
```

ID является каноническим, slug — только удобством. CLI ищет объект по полю
`id`, а не строит путь из ID. Ручное перемещение файла допустимо. Slug
нормализуется через Unicode NFKC и сохраняет буквы и цифры любого алфавита:
например, `Тестовый вопрос` превращается в `тестовый-вопрос`, а не в `node`.

### 7.2. Полный пример

```markdown
---
format_version: 1
id: hyp-01K2M7K6R9JAFWQ3NRM8V4C1TX
kind: hypothesis
title: Более длинный контекст повышает recall
status: active
summary: Проверяется влияние окна 32k по сравнению с 8k.
statement: >-
  Увеличение контекста с 8k до 32k повышает recall минимум на 10%.
falsification_criteria: >-
  Рост recall меньше 10% на заранее зафиксированном benchmark.
assumptions:
  - Состав benchmark не меняется между запусками.
tags:
  - retrieval
  - context
aliases:
  - H-context-window
created_at: 2026-08-16T10:30:00+07:00
created_by:
  kind: human
  id: fedor
updated_at: 2026-08-16T10:30:00+07:00
updated_by:
  kind: human
  id: fedor
relations:
  - id: rel-01K2M8C58E09VJMMA2XT67F1RQ
    kind: addresses
    target: que-01K2M7J94Y9R1JY8G5C2Q7F8BA
    created_at: 2026-08-16T10:30:00+07:00
    created_by:
      kind: human
      id: fedor
---

# Более длинный контекст повышает recall

## Мотивация

Свободный Markdown-текст, таблицы, формулы, изображения и Obsidian-ссылки.

## Заметки

Связан с экспериментом [[exp-01K2M8F5--context-window-benchmark]].
```

### 7.3. Markdown- и Obsidian-ссылки

Wiki-links в Markdown body удобны человеку, но не являются каноническими
семантическими рёбрами. Причины:

- у wiki-link нет обязательного типа;
- ссылка зависит от имени файла;
- из текста трудно надёжно извлечь rationale и provenance;
- обычное упоминание не всегда означает научную зависимость.

В будущем lint может находить wiki-links без соответствующих typed relations,
но автоматически превращать их в связи MVP не будет.

### 7.4. Правила сериализации

- YAML читается только safe parser без выполнения пользовательских тегов;
- допустимо только JSON-совместимое подмножество YAML 1.2;
- anchors, aliases, merge keys, пользовательские tags и сложные keys запрещены;
- дублирующиеся YAML keys считаются ошибкой;
- слова вроде `yes`, `no`, `on` и `off` не преобразуются в boolean неявно;
- timestamps после разбора представлены строками ISO 8601 и проверяются схемой;
- timestamps записываются в ISO 8601 с часовым поясом;
- body сохраняется без смыслового изменения при обновлении metadata;
- порядок пользовательских списков сохраняется;
- порядок top-level полей нормализуется ядром;
- форматирование всего vault выполняется только явной командой;
- запись одного файла выполняется через временный файл и atomic replace;
- перед заменой новая версия полностью валидируется;
- пути и symlinks не должны позволять запись за пределы vault.

### 7.5. JSON Schema

Файловый контракт `format_version: 1` опубликован как две JSON Schema Draft
2020-12 внутри Python package:

- `node-v1.schema.json` описывает декодированный YAML front matter всех десяти
  Node kinds;
- `project-v1.schema.json` описывает `research.yaml`.

Схемы доступны без runtime-зависимости от JSON Schema validator:

```python
from research_framework import node_schema, project_schema

node_contract = node_schema()
project_contract = project_schema()
```

Каждый вызов возвращает независимый `dict`. Схемы фиксируют локальную структуру,
required-поля, JSON-типы, ID patterns и enums. Они не проверяют уникальность ID
между файлами, существование relation targets, relation matrix, policies и
циклы: эти правила требуют снимка всего проекта и остаются ответственностью
`Project.validate()` и `rf validate`.

Schema resources версионируются вместе с файловым форматом. Изменение их
допустимого контракта требует тех же правил совместимости и миграции, что и
изменение YAML front matter.

## 8. Загрузка проекта и представление в памяти

### 8.1. Последовательность загрузки

1. Найти `research.yaml`, начиная с текущего каталога и двигаясь к корню.
2. Проверить версию конфигурации.
3. Рекурсивно найти `*.md` в `vault`.
4. Прочитать front matter каждого файла.
5. Построить типизированные Node.
6. Проверить уникальность ID и aliases.
7. Преобразовать `relations` в Edge.
8. Построить исходящий и входящий adjacency index в памяти.
9. Выполнить referential и semantic validation.
10. Вернуть immutable `GraphSnapshot` и список diagnostics.

Порядок файловой системы не должен влиять на результат. Публичные выборки по
умолчанию сортируются по `created_at`, затем по `id`.

### 8.2. Основные доменные типы

```text
Actor
Node
  Question
  Hypothesis
  Claim
  Experiment
  Run
  Evidence
  Assessment
  Source
  Artifact
  Decision
Edge
GraphSnapshot
Diagnostic
ProjectConfig
```

Конкретные Node реализуются как discriminated union по полю `kind`. Это даёт
общие графовые операции и строгую проверку специальных полей.

### 8.3. Операции GraphSnapshot

MVP предоставляет:

- `get_node(id_or_alias)`;
- `get_edge(id)`;
- `list_nodes(kind=None, status=None, tags=None)`;
- `outgoing(node_id, kinds=None)`;
- `incoming(node_id, kinds=None)`;
- `neighbors(node_id, direction="both", kinds=None)`;
- `traverse(node_id, depth, direction="both", kinds=None)`;
- `find_path(source_id, target_id, kinds=None, max_depth=None)`;
- `export_json()`.

GraphSnapshot не изменяется после построения. Мутации выполняются через Project
service, после чего вызывающий код может получить новый snapshot. Это не
позволяет случайно изменить только in-memory граф и забыть сохранить файлы.

## 9. Слои приложения

Предлагаемая структура Python-пакета:

```text
src/research_framework/
├── domain/
│   ├── nodes.py
│   ├── edges.py
│   ├── graph.py
│   ├── enums.py
│   └── errors.py
├── application/
│   ├── project.py
│   ├── commands.py
│   └── queries.py
├── storage/
│   ├── repository.py
│   ├── file_repository.py
│   ├── markdown_codec.py
│   └── discovery.py
├── validation/
│   ├── validator.py
│   ├── structural.py
│   ├── semantic.py
│   └── graph_rules.py
├── presentation/
│   ├── terminal.py
│   └── html_graph.py
├── cli/
│   ├── main.py
│   ├── node.py
│   ├── link.py
│   └── graph.py
└── __init__.py
```

### 9.1. Domain

Не зависит от CLI, файловой системы и конкретной YAML-библиотеки. Содержит
модели и инварианты графа.

### 9.2. Storage

Реализует интерфейс Repository:

```python
class Repository(Protocol):
    def load(self) -> GraphSnapshot: ...
    def create_node(self, draft: NodeDraft) -> Node: ...
    def update_node(self, node_id: str, patch: NodePatch) -> Node: ...
    def archive_node(self, node_id: str) -> Node: ...
    def add_edge(self, draft: EdgeDraft) -> Edge: ...
    def remove_edge(self, edge_id: str) -> None: ...
    def validate(self) -> list[Diagnostic]: ...
```

В MVP существует только `FileRepository`. Интерфейс нужен не для будущей БД как
цели, а для отделения файлового codec от доменной логики и удобного тестирования.

### 9.3. Application

Оркестрирует use cases:

- разрешает ID и aliases;
- проверяет optimistic revision;
- применяет доменные правила;
- вызывает Repository;
- возвращает типизированный результат и diagnostics.

### 9.4. Presentation

Преобразует один и тот же результат в:

- терминальные таблицы и деревья;
- стабильный JSON;
- детерминированный GraphViewModel;
- автономный интерактивный Canvas HTML для полного графа или локальной
  окрестности.

Presentation не читает исследовательские файлы напрямую: получает immutable
GraphSnapshot. HTML не зависит от CDN, не исполняет пользовательский Markdown
как markup и не меняет canonical vault. Payload встраивается как escaped JSON,
а пользовательские значения выводятся через `textContent`. Интерактивные
фильтры по tags (`any`/`all`), kind, status и relation kind выполняются только в
браузере и не меняют GraphViewModel. Selection карточки не зависит от Canvas
visibility: скрытая фильтром Node остаётся доступной через relations.

## 10. Python API

Публичный API должен быть небольшим и не раскрывать детали YAML-парсера или
CLI-фреймворка.

### 10.1. Открытие и чтение

```python
from pathlib import Path

from research_framework import Project, NodeKind

project = Project.open(Path("."))
graph = project.snapshot()

hypotheses = graph.list_nodes(
    kind=NodeKind.HYPOTHESIS,
    status="active",
    tags={"retrieval"},
)

hypothesis = graph.get_node("H-context-window")
evidence = graph.incoming(hypothesis.id, kinds={"supports", "challenges"})
```

### 10.2. Создание узла

```python
from research_framework import Actor, HypothesisDraft

hypothesis = project.create_node(
    HypothesisDraft(
        title="Более длинный контекст повышает recall",
        statement="Окно 32k повышает recall минимум на 10%.",
        falsification_criteria="Рост recall меньше 10%.",
        tags={"retrieval", "context"},
    ),
    actor=Actor.human("fedor"),
)
```

Узлы с обязательными исходящими связями создаются вместе с ними одной атомарной
операцией:

```python
from research_framework import Actor, EdgeKind, RelationDraft, RunDraft

run = project.create_node(
    RunDraft(
        title="Benchmark run",
        started_at="2026-08-17T12:00:00+07:00",
        outcome="running",
    ),
    actor=Actor.agent("benchmark-runner", run_id="agent-run-42"),
    initial_relations=(
        RelationDraft(
            kind=EdgeKind.INSTANCE_OF,
            target=experiment_id,
        ),
    ),
)
```

`initial_relations` содержит только исходящие связи нового узла. Приложение
разрешает ID, alias или однозначный префикс target, генерирует ID и audit-поля
связей и проверяет будущий граф до записи. Операция либо создаёт один полностью
валидный Markdown-файл, либо не изменяет проект.

Return types мутаций остаются компактными (`Node`, `Edge` или `None`), а warnings
последней успешной операции доступны отдельно:

```python
edge = project.add_edge(...)
warnings = project.last_diagnostics()
```

Перед началом следующей мутации diagnostics очищаются. Ошибочная мутация
возвращает diagnostics через `ValidationFailed` и не оставляет candidate warnings
в `last_diagnostics()`.

### 10.3. Создание связи

```python
edge = project.add_edge(
    source=evidence_id,
    kind="supports",
    target=hypothesis.id,
    rationale="Recall вырос на 13%.",
    actor=Actor.agent("evaluation-agent", run_id="run-184"),
)
```

### 10.4. Изменение с optimistic concurrency

При чтении Node содержит вычисленный `revision` — SHA-256 исходного файла.
Revision не записывается в Markdown.

```python
node = project.snapshot().get_node(hypothesis.id)

project.update_node(
    node.id,
    patch={"summary": "Обновлённое summary"},
    expected_revision=node.revision,
    actor=Actor.human("fedor"),
)
```

Если файл изменился после чтения, операция завершается `RevisionConflict`, а не
перезаписывает чужую работу. Это особенно важно для нескольких агентов.

Перед записью `create_node`, `update_node`, `add_edge` и `remove_edge` строят
полные метаданные будущего source-документа. Structural rules проверяются на
кандидате, uniqueness и referential rules — по индексам уже валидного snapshot,
а возможный новый cycle — поиском пути только из затронутого target обратно к
source. Полный vault для каждой мутации повторно не читается.

Ошибка structural, referential, semantic или graph validation не меняет ни
одного байта и не обновляет snapshot. После atomic write Node и его outgoing
edges разбираются из уже сериализованных bytes и публикуются copy-on-write:
выданные ранее snapshots остаются неизменными, а серия мутаций без получения
промежуточных snapshots обновляет только затронутые индексы. При позднем сбое
публикации исходные байты source-файла восстанавливаются атомарно.

### 10.5. Каноническое форматирование

```python
result = project.format(check=True)

if result.changed_paths:
    applied = project.format()
```

`FormatResult` содержит число проверенных Node-файлов, абсолютные пути файлов с
отличиями и признак фактически применённых изменений. `check=True` никогда не
пишет на диск. Обычный режим меняет только YAML front matter; Markdown body и
`PROJECT.md` сохраняются байт-в-байт.

Перед первой записью приложение валидирует проект и готовит канонические версии
всех Node-файлов. Для каждого кандидата повторно проверяется исходная revision.
При concurrent edit возникает `RevisionConflict`; при позднем сбое уже
перезаписанные файлы откатываются к исходным байтам. Успешная операция обновляет
snapshot и публикует warnings через `last_diagnostics()`.

### 10.6. Ошибки Python API

Публичная иерархия исключений:

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

Сообщение предназначено человеку, а поля исключения содержат машинно читаемый
код и diagnostics.

## 11. CLI

Рабочее имя executable: `rf`. Если при публикации обнаружится конфликт имён,
оно может быть заменено без изменения Python API и файлового формата.

### 11.1. Команды MVP

```text
rf init [PATH]

rf node create KIND
rf node show ID
rf node list
rf node update ID
rf node archive ID

rf link add SOURCE KIND TARGET
rf link list ID
rf link remove EDGE_ID

rf graph show [ID]
rf graph traverse ID
rf graph path SOURCE TARGET
rf graph export
rf graph render [--focus REF] [--depth N] [--output FILE]

rf validate
rf format [--check]
```

Примеры:

```bash
rf node create hypothesis \
  --title "Более длинный контекст повышает recall" \
  --statement "Окно 32k повышает recall минимум на 10%." \
  --falsification-criteria "Рост меньше 10%." \
  --tag retrieval \
  --actor fedor

rf node create run \
  --title "Benchmark run" \
  --started-at "2026-08-17T12:00:00+07:00" \
  --outcome running \
  --instance-of exp-01K2M7K6 \
  --actor fedor

rf link add evd-01K2M7M4 supports hyp-01K2M7K6 \
  --rationale "Recall вырос на 13%." \
  --actor fedor

rf node list --kind hypothesis --status active --tag retrieval
rf graph traverse hyp-01K2M7K6 --direction both --depth 2
rf graph export --format json
rf validate
rf format --check
```

Префиксы ID принимаются, только если однозначно разрешаются. Неоднозначный
префикс возвращает ошибку со списком кандидатов.

### 11.2. Режим для человека

По умолчанию CLI:

- выводит компактные таблицы и деревья;
- пишет warnings в stderr;
- по явному `--edit` открывает `$EDITOR` для Markdown body;
- также принимает Markdown body через `--body` или `--body-file`;
- никогда не выполняет Git-команды автоматически.

Флаги `--body`, `--body-file` и `--edit` взаимоисключающие. Ошибка запуска или
ненулевой exit code редактора отменяют создание узла до файловой мутации.

### 11.3. Режим для программ и агентов

Каждая команда, возвращающая данные, поддерживает `--json`. Мутации принимают
полный input через JSON-файл или stdin:

```bash
rf node create hypothesis --from-json hypothesis.json --json
rf link add --from-json - --json < relation.json
rf node show hyp-01K2M7K6 --json
```

JSON input для `node create` может включать те же начальные связи:

```json
{
  "title": "Benchmark run",
  "started_at": "2026-08-17T12:00:00+07:00",
  "outcome": "running",
  "initial_relations": [
    {
      "kind": "instance_of",
      "target": "exp-01K2M7K6"
    }
  ],
  "actor": {
    "kind": "agent",
    "id": "benchmark-runner",
    "run_id": "agent-run-42"
  }
}
```

Для human-oriented режима предусмотрены `--instance-of`, повторяемые
`--derived-from`, `--assesses` и `--based-on`.

В JSON-режиме:

- интерактивные prompts запрещены;
- stdout содержит только один JSON document;
- diagnostics и результат имеют стабильную схему;
- логи отправляются в stderr;
- timestamps и enums не локализуются.

JSON input использует закрытые строгие envelopes: неизвестные поля запрещены,
числа и boolean не приводятся к строкам, одна строка не приводится к массиву,
а необязательное значение следует опустить вместо передачи `null`. Ошибка
формы запроса даёт `invalid_arguments` и exit code `2` до файловой записи;
ошибка предметной или graph validation — exit code `3`, также без частичной
мутации. Точный контракт приведён в [automation.md](automation.md).

Успешные mutation-команды передают warnings из того же candidate validation в
верхнеуровневом массиве `warnings`. В human-oriented режиме те же warnings
печатаются в stderr и не меняют exit code `0`.

Успешный ответ:

```json
{
  "ok": true,
  "data": {
    "id": "hyp-01K2M7K6R9JAFWQ3NRM8V4C1TX",
    "kind": "hypothesis"
  },
  "warnings": []
}
```

Ошибка:

```json
{
  "ok": false,
  "error": {
    "code": "target_not_found",
    "message": "Relation target does not exist",
    "details": {
      "target": "hyp-missing"
    }
  }
}
```

### 11.4. Форматирование

`rf format` явно приводит YAML front matter всех Node-файлов к стабильному
порядку полей и единому представлению restricted YAML. Команда не форматирует
Markdown body и не считает `PROJECT.md` узлом. Весь результат готовится до
первой записи; поздний сбой приводит к rollback уже изменённых файлов.

`rf format --check` выполняет ту же проверку без записи. Канонический проект
даёт exit code `0`. Если нужны изменения, команда возвращает exit code `1` и
ошибку `formatting_required`; в `details.paths` перечислены относительные пути.
Повторный `rf format` идемпотентен.

Успешный JSON-ответ содержит `formatted`, `check`, `checked_files` и
`changed_files`, а также обычный верхнеуровневый массив `warnings`.

### 11.5. Exit codes

| Code | Значение |
|---:|---|
| 0 | Успех |
| 1 | Проверка состояния не прошла (например, format drift) или внутренняя ошибка |
| 2 | Неверные CLI arguments |
| 3 | Ошибка валидации проекта или input |
| 4 | Объект не найден или ссылка неоднозначна |
| 5 | Revision conflict |
| 6 | Неподдерживаемая версия формата |

## 12. Валидация и diagnostics

Валидация разделяется на четыре уровня.

### 12.1. Syntax

- корректность YAML front matter;
- наличие закрывающего delimiter;
- безопасные YAML-типы;
- корректность timestamps и ID.

### 12.2. Structural

- обязательные общие поля;
- обязательные поля конкретного kind;
- допустимые enum;
- отсутствие неизвестных top-level полей;
- уникальность Node ID, aliases и Edge ID.

### 12.3. Referential and semantic

- target каждой связи существует;
- source и target соответствуют relation matrix;
- обязательные связи присутствуют;
- provenance evidence прослеживается;
- assessment содержит основания или явное исключение политики.

### 12.4. Graph rules

- запрещённые циклы;
- self-links;
- несколько `instance_of` у одного run;
- некорректные цепочки `supersedes`;
- ссылки на archived узлы как предупреждение.

Diagnostic имеет стабильную форму:

```text
severity: error | warning | info
code: dangling_relation
message: Relation target does not exist
path: research/evidence/evd-...md
node_id: evd-...
edge_id: rel-...
field: relations[0].target
suggestion: Create the target or remove the relation
```

`rf validate` не изменяет файлы. Ошибки дают ненулевой exit code, warnings — нет.
`rf format --check` также не изменяет файлы; неканоническое представление даёт
`formatting_required`, а validation errors сохраняют обычный exit code `3`.

## 13. Git и совместная работа

### 13.1. Что хранится в Git

- `research.yaml`;
- Markdown-узлы;
- небольшие артефакты по решению команды;
- схемы, policies и документация проекта.

### 13.2. Что не является частью канонического состояния

- локальный поисковый индекс;
- кеш распарсенного графа;
- временные файлы атомарной записи;
- персональные настройки редактора;
- runtime-логи агентов.

### 13.3. Снижение merge-конфликтов

- один узел на файл;
- исходящее ребро хранится только у source;
- нет центрального счётчика ID;
- backlinks вычисляются, а не записываются;
- autogenerated reports не обновляются при каждой мутации;
- CLI не переформатирует Markdown body без явной команды;
- optimistic revision предотвращает тихую локальную перезапись.

### 13.4. Поведение при Git-конфликте

Ядро не пытается автоматически разрешать конфликтные маркеры. Файл с
`<<<<<<<`, `=======` или `>>>>>>>` во front matter считается невалидным, а CLI
показывает путь и просит сначала разрешить Git-конфликт.

## 14. Производительность без БД

Открытие Project и явный `validate` сканируют vault целиком. Стоимость:

```text
загрузка: O(число файлов + размер front matter)
построение adjacency: O(V + E)
neighbors: O(степень узла)
traverse: O(посещённые V + E)
обычная мутация: O(размер source + затронутые adjacency/aliases)
проверка нового cycle: O(достижимое из target поддерево)
```

Mutation path не выполняет повторный file scan, full validation или reload.
Project использует copy-on-write snapshot: полная неглубокая копия индексов
нужна только после того, как текущий snapshot был выдан вызывающему коду и его
неизменяемость нужно сохранить. При пакетном наполнении через последовательные
`create_node` без запроса snapshot между вызовами индекс обновляется на месте.
Экземпляр `Project` не отслеживает произвольные внешние изменения остальных
файлов: после ручной правки или работы другого процесса вызывающий код должен
создать новую session через `Project.open()`. Revision изменяемого source
проверяется непосредственно перед atomic write независимо от этого.

Markdown body можно загружать лениво: сначала читать metadata и offsets, а body
открывать только для `show` или export. Это даст приемлемую работу на проектах
с тысячами узлов без дополнительного постоянного состояния.

Постоянный индекс для ускорения самого открытия следует добавлять после
измерений. Возможный будущий индекс:

```text
.research-cache/index.sqlite
```

Он обязан:

- находиться в `.gitignore`;
- содержать hash/indexed revision каждого файла;
- автоматически обновляться или пересобираться;
- не принимать пользовательские записи напрямую;
- не менять результат запросов по сравнению с чистым file scan.

## 15. Версионирование формата

`format_version` версионирует структуру файлов, а не версию Python-пакета.

Правила:

- reader обязан читать текущую версию;
- более новая неизвестная версия завершается явной ошибкой;
- миграция никогда не происходит неявно;
- будущая команда `rf migrate --to N` сначала поддержит `--dry-run`;
- миграция должна создавать Git-readable diff;
- старые IDs не меняются при миграции.

Для MVP существует только `format_version: 1`, сама команда миграции не нужна.

## 16. Безопасность и надёжность

- использовать safe YAML loader;
- запрещать произвольные Python/YAML object tags;
- валидировать ID до построения пути;
- не следовать symlink при записи за пределы vault;
- не выполнять код, указанный в experiment или artifact;
- не скачивать URI автоматически;
- не выполнять Git-команды автоматически;
- сначала валидировать, затем атомарно заменять файл;
- не удалять Node физически в MVP, а переводить в `archived`;
- требовать явную команду для удаления Edge;
- возвращать conflict при несовпадении expected revision.

## 17. Предлагаемый технологический стек

Это реализационные предложения, не часть долговременного файлового контракта:

- Python 3.11+;
- `pydantic` для discriminated models, validation и JSON Schema;
- `typer` для CLI;
- YAML-библиотека с safe loading и сохранением порядка;
- `rich` только в presentation layer;
- `pytest` для тестов;
- `ruff` и статическая проверка типов;
- `uv` или стандартная packaging-конфигурация для окружения.

Файловая схема не должна зависеть от особенностей Pydantic или Typer. При смене
библиотеки существующие исследовательские проекты должны продолжить работать.

## 18. Стратегия тестирования

### 18.1. Domain unit tests

- допустимые и недопустимые пары relation;
- циклы и обход графа;
- разрешение ID, prefix и aliases;
- неизменяемость GraphSnapshot;
- сортировка и детерминированность результатов.

### 18.2. Codec golden tests

- чтение примеров каждого kind;
- сохранение Markdown body;
- YAML edge cases;
- parse → serialize → parse сохраняет семантическую модель;
- неизвестные поля и новые format versions дают понятные ошибки.

### 18.3. Repository tests

- discovery файлов;
- duplicate IDs;
- atomic write;
- revision conflict;
- ручное перемещение файла;
- запрет выхода за vault.

### 18.4. CLI integration tests

- полный сценарий init → create → link → traverse → validate;
- JSON stdout не содержит декоративного текста;
- стабильные exit codes;
- одинаковый результат CLI и Python API.

### 18.5. Example project

В репозитории нужен небольшой fixture-проект, содержащий:

```text
question
  └── hypothesis
        ├── experiment ── run ── evidence
        ├── supporting evidence
        ├── challenging evidence
        └── assessment
```

Он одновременно служит integration fixture и живой документацией формата.

## 19. Критерии готовности MVP

MVP считается готовым, если выполняются все условия:

1. Новый проект создаётся командой `rf init` без БД.
2. Каждый тип Node можно создать через Python API.
3. Основные типы Node можно создать через CLI.
4. Один и тот же проект можно вручную редактировать как Markdown vault.
5. Typed relation можно добавить и удалить через Python и CLI.
6. Входящие связи вычисляются без записи backlinks.
7. GraphSnapshot поддерживает filter, neighbors, traverse и path.
8. `rf validate` находит битые ссылки, неверные типы и запрещённые циклы.
9. CLI имеет стабильный JSON-режим для AI-агентов.
10. Конкурирующее изменение файла обнаруживается через revision conflict.
11. Все мутации создают небольшие понятные Git diff.
12. Удаление любого кеша не приводит к потере данных.
13. Python API, CLI и файловый формат покрыты тестами.
14. Пример проекта проходит validation без warnings.

## 20. Последовательность разработки после согласования

### Этап 1. Контракт и каркас

- создать Python package;
- зафиксировать модели и enums;
- добавить JSON Schema и примеры файлов;
- настроить тесты и статические проверки.

### Этап 2. Read-only файловое ядро

- реализовать Markdown/YAML codec;
- discovery проекта;
- построение GraphSnapshot;
- structural и referential validation;
- Python read API.

### Этап 3. Мутации

- создание и изменение Node;
- архивирование;
- создание и удаление Edge;
- atomic writes;
- optimistic revisions.

### Этап 4. CLI

- human-readable output;
- JSON mode;
- graph traversal и export;
- exit codes и diagnostics.

### Этап 5. Стабилизация MVP

- integration fixture;
- end-to-end tests;
- документация пользовательского workflow;
- проверка реального Git diff на типичных изменениях.

## 21. Утверждённые решения

1. **Формат:** Markdown + ограниченный JSON-совместимый YAML 1.2 front matter
   является каноническим физическим форматом; JSON используется для машинных
   интерфейсов и экспорта.
2. **Связи:** исходящие relations хранятся внутри source-файла, а не отдельными
   файлами.
3. **ID:** используются prefix + ULID; `H-001` допускается только как alias.
4. **Типы MVP:** question, hypothesis, claim, experiment, run, evidence,
   assessment, source, artifact и decision.
5. **Истина:** отдельного `fact` нет; используется claim + assessment + evidence.
6. **Статус:** lifecycle Node отделён от эпистемического verdict assessment.
7. **API:** CLI является тонким адаптером к публичному Python application layer.
8. **БД:** отсутствует в MVP; будущий индекс всегда производный и удаляемый.
9. **Удаление:** Node только архивируются; физическое удаление не входит в MVP.
10. **Git:** ядро не выполняет commit/pull/push и не разрешает конфликты.

Решения подтверждены перед началом разработки. Изменения публичного файлового
контракта далее оформляются явно вместе с миграцией версии формата.
