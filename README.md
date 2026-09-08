# Research Framework

Git-native, text-first граф исследований. Узлы хранятся как Markdown с
JSON-совместимым YAML front matter, связи образуют типизированный граф, а Git
служит историей и механизмом совместной работы. База данных не требуется.

Фреймворк предоставляет:

- human-oriented CLI `rf` с таблицами, графами и `$EDITOR`;
- строгий JSON-интерфейс для агентов, скриптов и CI;
- публичный Python API и неизменяемые снимки графа;
- автономную интерактивную HTML-визуализацию без сервера и CDN;
- structural, referential, semantic и graph validation;
- атомарные мутации, optimistic revisions и локальные Git diff;
- JSON Schema Draft 2020-12 для файлового контракта.

## Документация

- [Полный справочник возможностей](docs/reference.md)
- [Workflow для человека](docs/workflow.md)
- [Агенты, скрипты и JSON API](docs/automation.md)
- [Архитектура и принятые решения](docs/architecture.md)
- [Тестовый контракт](docs/testing.md)

## Быстрый старт

Требуется Python 3.11+ и `uv`. Для работы с CLI из текущего checkout:

```bash
uv tool install --editable /path/to/research-framework
rf --help
```

В уже существующем Git-репозитории создайте отдельный research-root:

```bash
cd /path/to/your-project
rf init research-graph --title "Исследование проекта" --default-language ru
cd research-graph

rf node create question \
  --title "Улучшает ли изменение результат?" \
  --question "Повышает ли изменение целевую метрику?" \
  --alias Q-main \
  --actor fedor

rf validate
rf graph render
```

Долгие команды автоматически показывают progress bar в интерактивном
терминале. Для логов его можно принудительно включить корневым флагом
`rf --progress COMMAND ...` или отключить через `rf --no-progress COMMAND ...`.
В JSON-режиме progress автоматически отключён, но явный `--progress` выводит
его в `stderr`, не затрагивая JSON document в `stdout`.

Тело существующего Node можно безопасно изменить через редактор:

```bash
rf node edit REF --actor fedor
```

Команда открывает `$EDITOR` с текущим Markdown и сохраняет результат атомарно с
revision check. Для агентов поле `body` доступно в JSON-вводе `node update`.

После первого открытия создаётся удаляемый `.research-cache/index-v3.sqlite3`.
Он ускоряет следующие запуски, не является canonical state и автоматически
перестраивается при изменении Node, конфигурации или формата индекса.

Индекс используют все команды, включая `rf validate` и `rf format`: файл
считается неизменившимся, если совпали path, size, `mtime_ns`, `ctime_ns` и
inode. `rf validate --full` игнорирует индекс и заново декодирует каждый файл;
результат обязан совпадать с обычным запуском.

`rf node show REF` находит Node через индекс и читает только его файл, не строя
весь граф. Целостность графа в целом проверяет `rf validate`.

`rf init` не изменяет непустой каталог. Команды ищут `research.yaml` от текущей
директории вверх, поэтому при вложенном размещении запускайте их из
`research-graph/`.

`rf graph render` создаёт `research-graph.html` рядом с `research.yaml`.
Откройте его обычным браузером: внутри доступны pan/zoom, перетаскивание узлов,
поиск, выбор интересующих тегов, остальные фильтры и карточки с metadata, body
и связями. Режим `linked context` оставляет рядом с выбранными Hypothesis/Claim
их Assessment, Evidence, Run и другой связанный контекст. Файл полностью
автономен. Индикатор `Layout` показывает ход фоновой раскладки и меняется на
`Layout ready`, когда вычисления завершены.

## Разработка фреймворка

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```
