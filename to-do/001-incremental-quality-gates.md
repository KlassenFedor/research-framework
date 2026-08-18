# TODO-001 — Инкрементальные quality gates для больших графов

- **Статус**: proposed
- **Приоритет**: performance / scalability
- **Целевой момент**: когда типичный граф превышает 5–10 тысяч Nodes либо
  обязательный quality gate стабильно занимает больше 60–120 секунд
- **Ограничение первой итерации**: без новой БД, native-зависимости или
  C-backed parser; сначала использовать алгоритмические оптимизации и текущий
  производный индекс

## 1. Проблема

На измеренном графе с пропорциональным ростом числа relations операции
масштабировались линейно как минимум до 14 680 Nodes и примерно 25 000 edges.
Квадратичного поведения не обнаружено, а память росла достаточно медленно,
поэтому ближайшее ограничение — latency обязательных проверок, а не RAM.

Наблюдавшиеся удельные стоимости на одном representative corpus:

| Операция | Приблизительная стоимость |
|---|---:|
| `node show` / `node list` | 0.39 ms / Node |
| `validate` | 3.14 ms / Node |
| `format --check` | 9.50 ms / Node |
| полный project quality gate | 14.9 ms / Node |
| повторный show + update | 0.80 ms / Node |
| память загруженного графа | 11 KiB / Node |

Эти числа являются исходной эмпирической точкой, а не универсальным SLA:
результат зависит от размера front matter, body, плотности связей, файловой
системы и CPU. Важен устойчивый вывод:

1. `format --check` оказался самым дорогим framework-owned этапом gate;
2. следующим по стоимости является полная validation;
3. рост пока линейный, поэтому следует уменьшать постоянную стоимость на Node,
   а не преждевременно менять файловую модель;
4. когда gate занимает минуты, пользователи начинают запускать его реже, что
   повышает вероятность накопления ошибок перед commit/CI.

## 2. Текущий механизм и источник лишней работы

На момент постановки задачи CLI сначала выполняет `Project.open()`, который
проверяет граф и строит snapshot с использованием `.research-cache`.
После этого `Project.format(check=True)`:

1. снова вызывает полную `validate()` с чтением canonical Markdown;
2. повторно делает discovery всех Node-файлов;
3. читает каждый Node целиком;
4. декодирует Markdown/YAML;
5. сериализует canonical представление;
6. повторно декодирует сериализованный результат;
7. сравнивает bytes с исходным файлом.

Для неизменившегося и уже проверенного проекта почти вся эта работа
повторяется при каждом gate. Текущий persistent index уже хранит fingerprint,
revision, metadata, relations и body offset, но не хранит результат проверки
canonical formatting или достаточно подробное состояние incremental
validation.

## 3. Цели

1. Сделать warm `format --check` почти пропорциональным числу изменившихся
   файлов, сохранив discovery/stat полного vault для обнаружения add/remove.
2. Уменьшить стоимость warm validation без изменения набора, порядка и
   структуры diagnostics.
3. Сохранить точное равенство результатов cold/full и warm/incremental путей.
4. Не превращать кеш в canonical state: его удаление или повреждение должно
   приводить только к безопасному full rebuild.
5. Сохранить atomic write, optimistic revision, symlink/path protection и
   детерминированный output.
6. Сделать производительность наблюдаемой: progress и machine-readable result
   должны показывать число cached, decoded, validated и formatted Nodes.

## 4. Не цели первой итерации

- разбиение одного исследования на независимые хранилища или подграфы;
- изменение Markdown/YAML file format;
- обязательный daemon или долгоживущий server process;
- отказ от полной проверки как доступной контрольной операции;
- полнотекстовый поисковый индекс;
- оптимизация внешних project-specific scripts, не входящих во фреймворк;
- снижение RAM любой ценой: задержка является более ранним ограничением.

## 5. Этап 0 — воспроизводимый benchmark и profiling

До изменения алгоритма добавить benchmark harness, генерирующий валидные
синтетические графы без привязки к предметной области конкретного проекта.

Матрица:

| Измерение | Значения |
|---|---|
| Nodes | 1k, 5k, 10k, 20k, 50k |
| Relations / Node | 0, 1.5–2, 5, 10 |
| Изменившиеся файлы | 0%, 0.1%, 1%, 10%, 100% |
| Сценарий | cold cache, warm cache, corrupt cache, config change |
| Операция | open/show/list, validate, format check/apply, repeated mutations |

Отдельно профилировать:

- discovery и `stat`;
- чтение bytes и UTF-8 decode;
- restricted YAML decode;
- structural validation;
- построение ID/alias/relation indexes;
- referential и semantic checks;
- cycle checks при различной плотности edges;
- decode → encode → decode formatter path;
- JSON cache load/write;
- CLI startup отдельно от application time.

Benchmark не должен дублировать один Node с одинаковыми IDs или создавать
нереалистично пустой граф. Генератор обязан сохранять валидность, уникальность
ID/aliases и заданную плотность relations.

Абсолютные time limits не добавлять в обычный CI: там проверять количество
read/decode/encode операций и асимптотику. Временные показатели запускать
отдельным performance job или вручную на простаивающей reference machine.

## 6. Этап 1 — инкрементальный `format --check`

### 6.1. Расширение производного индекса

Для каждой успешно проверенной записи хранить дополнительно:

- source fingerprint и SHA-256 revision;
- `formatter_version` / `codec_version`;
- `is_canonical`;
- при `is_canonical == false` — достаточно данных, чтобы вернуть путь в
  `changed_paths` без повторной сериализации неизменившегося файла;
- при необходимости hash canonical bytes, но не сами body или полную вторую
  копию Node-файла.

Изменение cache schema должно увеличить её версию. Старый, неизвестный или
неполный кеш игнорируется и перестраивается; миграция derived cache не нужна.

### 6.2. Warm check

Алгоритм для `format(check=True)`:

1. Выполнить discovery и собрать fingerprints.
2. Обнаружить добавленные, удалённые, переименованные и изменившиеся paths.
3. Для неизменившихся entries с совпавшей formatter/codec version использовать
   cached `is_canonical`.
4. Только для cache miss/changed entries выполнить stable read с проверкой
   `stat → read → stat`, decode, encode, проверку encoded output и byte compare.
5. Вернуть те же `checked_files` и детерминированно отсортированные
   `changed_paths`, что и полный проход.
6. Атомарно обновить кеш только после успешной обработки всех entries.

Warm check неизменившегося canonical vault не должен читать, декодировать или
сериализовывать ни одного Markdown-файла.

### 6.3. Format apply

Для `format(check=False)`:

- cached canonical entries пропускаются;
- cached non-canonical entries перечитываются перед записью, поскольку нужны
  original и formatted bytes;
- непосредственно перед replace повторно проверяется revision;
- существующая all-or-rollback семантика сохраняется;
- после успеха cache entries обновляются новыми fingerprints/revisions и
  `is_canonical=true`;
- при concurrent edit, write failure или rollback cache не должен утверждать,
  что незавершённая версия canonical.

### 6.4. Устранение двойной проверки

Нельзя просто удалить `self.validate()` из formatter path. Сначала определить
и зафиксировать контракт:

- может ли formatter полагаться на validated snapshot, полученный тем же
  `Project.open()`;
- как обнаруживается external edit между open и format;
- как format вызывается напрямую из Python после долгоживущей session;
- должен ли CLI иметь объединённый `validate_and_format_check()` проход.

Предпочтительный результат — один discovery/fingerprint pass и переиспользование
одних decoded/cached metadata для validation и formatting, без окна, в котором
изменившийся файл остаётся незамеченным.

## 7. Этап 2 — инкрементальная validation

Выполнять по подэтапам, измеряя эффект каждого.

### 7.1. Переиспользование metadata без YAML decode

Первый безопасный вариант:

- использовать текущий persistent index для неизменившихся Nodes;
- декодировать только cache misses и изменившиеся файлы;
- каждый раз выполнять все global graph rules над объединёнными metadata в
  памяти;
- сохранить отдельный full path, который игнорирует кеш и читает источники.

Этот шаг не является полной incremental validation, но отделяет стоимость
парсинга от стоимости graph rules и даёт корректную базу для следующего шага.

### 7.2. Кеш локальных diagnostics

Кешировать только diagnostics, зависящие от одного документа, с ключом:

```text
(source_revision, schema_version, validator_version, relevant_config_signature)
```

Для неизменившихся Nodes повторно использовать syntax/structural results.
Global diagnostics на этом этапе продолжать вычислять полностью.

### 7.3. Пересчёт затронутой области графа

После профилирования выделить dependency map правил:

| Изменение | Минимально затронутая область |
|---|---|
| ID/alias | изменённый Node, владельцы конфликтующих keys, references к старому/новому ID |
| исходящие relations | source, старые и новые targets, adjacency/cycle indexes |
| status target | target и все incoming relations к нему |
| kind | Node и все incoming/outgoing relation-matrix checks |
| policy/config | все Nodes, которых касается изменившееся правило |
| удаление Node | его входящие/исходящие edges, aliases и global indexes |
| добавление Node | uniqueness indexes, его relations и потенциальные cycles |

Для batch внешних изменений вычислять объединённое affected closure и только
затем запускать rules. Нельзя независимо валидировать несколько changed Nodes
против старого snapshot: их совместный эффект может создавать duplicate alias,
dangling relation или cycle.

Cycle validation требует отдельного доказательства корректности для добавления,
удаления и замены нескольких edges. Если incremental algorithm становится
сложнее и рискованнее полного iterative DFS, оставить полный cycle pass до
появления измеренного bottleneck.

### 7.4. CLI-контракт

Рекомендуемый контракт после доказательства эквивалентности:

```bash
rf validate          # exact incremental path с безопасным fallback
rf validate --full   # принудительный cold source audit
```

Альтернатива до накопления доверия — оставить `rf validate` полным, а
incremental режим включать явно. Выбор сделать по результатам profiling и
fault-injection tests, а не только по скорости.

## 8. Этап 3 — повторные мутации и batch workflow

После оптимизации gate повторно измерить серии из 10/100/1000 мутаций.
Отдельный CLI process на каждую операцию всё ещё платит за warm open, stat и
восстановление graph indexes.

Если это остаётся значимой долей времени, спроектировать machine-oriented batch
API, открывающее Project один раз:

```text
rf batch --from-json operations.json --json
```

До реализации определить:

- all-or-nothing либо per-operation atomicity;
- expected revision для каждого source;
- возможность ссылаться на Node, созданный ранее в том же batch;
- формат diagnostics/warnings и частичных результатов;
- предел размера batch и progress events;
- rollback при ошибке поздней операции.

Не вводить daemon только ради уменьшения startup, пока batch API решает тот же
сценарий проще и с меньшей скрытой statefulness.

## 9. Инвалидизация и корректность кеша

Cached result разрешено использовать, только если совпадают:

- cache schema version;
- project/config signature;
- codec, formatter, schema и validator versions, релевантные операции;
- relative path;
- `size`, `mtime_ns`, `ctime_ns`, inode;
- checksum самого cache document.

Обязательные свойства:

- кеш находится вне vault и игнорируется Git;
- кеш закрыт для пользовательской записи и не является authority;
- corrupt/truncated/tampered cache приводит к cold rebuild;
- symlink cache path не читается и не перезаписывается;
- read-only project работает без возможности записать кеш;
- запись кеша выполняется через temp file, `fsync` и atomic replace;
- source, изменившийся во время чтения, перечитывается или даёт явную ошибку;
- успешный результат incremental path byte-for-byte/diagnostic-for-diagnostic
  совпадает с full path;
- cache write failure не меняет exit code корректно выполненной операции.

## 10. Progress и machine-readable observability

Добавить отдельные progress phases либо уточнить сообщения:

```text
discovering
checking_cache
loading_changed
validating_local
validating_graph
checking_format
writing_cache
```

Не генерировать десятки тысяч обязательных terminal redraws; callback events
могут быть подробными, а renderer должен throttling-ить их.

Расширить результаты без нарушения существующих полей:

```json
{
  "checked_files": 10000,
  "cached_files": 9997,
  "decoded_files": 3,
  "changed_files": []
}
```

Явный `--progress` продолжает писать только в stderr, включая JSON mode.

## 11. Тестовый контракт

### Format

1. Первый check читает/декодирует каждый Node и создаёт cache state.
2. Второй неизменившийся check выполняет ноль Markdown read/decode/encode.
3. Изменение одного Node обрабатывает ровно один Markdown-файл.
4. Неизменившийся non-canonical Node остаётся в `changed_paths` из кеша.
5. Apply форматирует cached non-canonical Node и обновляет cache state.
6. Add/remove/rename обнаруживаются независимо от кеша.
7. Codec/formatter/config version change инвалидирует нужные entries.
8. CRLF, Unicode и большие body сохраняются с прежней семантикой.
9. Concurrent edit не перезаписывается.
10. Partial write и rollback оставляют cache консервативным.

### Validation

1. Incremental и full paths возвращают идентичные отсортированные diagnostics.
2. Проверяются single и multiple simultaneous changes.
3. Покрыты duplicate IDs/aliases/edge IDs, dangling targets, kind/status change,
   warnings, policies и add/remove cycles.
4. Config/schema/validator version changes корректно инвалидируют diagnostics.
5. Corrupt cache никогда не скрывает validation error.
6. `--full` не использует cached metadata или diagnostics.

### Performance contract

В обычных тестах проверять operation counts:

- warm unchanged format: `0` Node read/decode/encode;
- warm unchanged metadata load: `0` YAML decode;
- один changed Node: `1` read/decode и не более необходимого числа encode;
- mutation path не выполняет full vault reload;
- рост synthetic benchmark остаётся линейным при фиксированной edge density.

## 12. Критерии приёмки

Минимум для закрытия этапов 1–2:

1. На unchanged warm corpus `format --check` не читает Node contents и работает
   не более чем в `1.25×` от времени discovery + cache load.
2. При изменении `k` файлов число YAML decode/format операций равно `O(k)`, а не
   `O(V)`; полный stat/discovery `O(V)` допустим.
3. Framework-owned quality gate на representative 10k/≈20k-edge corpus ускорен
   не менее чем в `3×` относительно зафиксированного cold baseline.
4. Порог двух минут для framework-owned gate на той же reference machine
   отодвинут как минимум за 20k Nodes при исходной плотности edges.
5. На более плотных графах нет скрытой сверхлинейности без отдельного отчёта и
   объяснения конкретного graph rule.
6. Incremental/full результаты эквивалентны во всех contract и fault-injection
   tests.
7. Пиковая память warm path не увеличивается более чем на 20% без измеренного
   обоснования.
8. Существующие CLI/Python API, atomicity, revision, warnings и progress
   контракты не регрессируют.
9. Документация описывает cache invalidation, `--full`, recovery и способы
   диагностики производительности.

## 13. Решение о подграфах

Разделение хранилища рассматривать только после реализации и повторного замера
инкрементальных format/validation и, при необходимости, batch mutations.

Перед таким решением требуется отдельный design document для:

- межхранилищных IDs и relations;
- глобального разрешения aliases;
- traverse/path/render между partitions;
- совместной validation и versioning;
- atomic mutations через границы partitions;
- влияния на Git workflow и переносимость проекта.

Если после оптимизации quality gate остаётся линейным и укладывается в целевые
пороги, усложнять canonical модель подграфами не следует.

## 14. Definition of Done

- benchmark harness и исходные профили сохранены в репозитории;
- incremental formatter реализован и покрыт operation-count tests;
- выбранный validation path реализован с exact full fallback;
- cache schema версионирована и документирована;
- fault-injection и concurrency tests зелёные;
- получены cold/warm результаты на всей benchmark matrix;
- опубликована таблица до/после с V, E, edge density, changed fraction, wall
  time, CPU time, peak RSS и числом file/decode/encode операций;
- полный test/lint/type/build pipeline проходит;
- документация для людей и automation обновлена;
- решение о batch API и подграфах принято на основании новых измерений.
