# Stage 25.17.2 — карта, привязки, соединения и личные стили

## Реализованная модель

`MapMarker` — отдельная точка или оформление дома. Иконка не определяет семантику.

| Поле | Значение |
| --- | --- |
| `point_type` | building, network_node, cabinet, splice, pole, chamber, equipment, note |
| `building_link_role` | none, reference, located_at, represents |
| `visibility` | company / private |
| `owner_user_id` | серверный владелец private-записи; для company — NULL |
| `version` | версия для optimistic concurrency |

У `represents` хранимые координаты NULL; API и viewport получают точку из `Building`.
Частичный UNIQUE `(company_id, building_id) WHERE building_link_role='represents'`
защищает единственность основной метки. Стиль одного дома может отличаться между компаниями.
`reference/located_at` сохраняют собственные координаты и не перемещают/не скрывают дом.
Типы infrastructure — минимальная классификация точек, не новый инвентарный учёт Equipment.

Заметка по умолчанию личная. При наличии `addresses.manage` техническую точку можно
создать общей. `addresses.read` достаточно для собственных private-заметок,
private-соединений и личных стилей. Company context и владельца нельзя передать в payload.
Приватность проверяется в list/detail/CRUD, выборе концов, геометрии и зависимостях.
Администратор компании тоже не видит чужие личные записи.

## Каноническое расположение и перепривязка

Обновление точки дома из обычного address API и операции оформления использует
`services/building_coordinates.py:set_building_position`. Личная заметка не даёт права менять
общий дом. Для явного изменения из редактора метки передаётся:

```json
{
  "point_type": "building",
  "visibility": "company",
  "building_id": 42,
  "building_link_role": "represents",
  "name": "Дом 53",
  "building_position": {"latitude": 55.577276, "longitude": 38.245099}
}
```

Если `building_position` отсутствует, произвольные поля `latitude/longitude` черновика
не перемещают основной дом. NULL остаётся NULL, не преобразуется в 0/0.

Занятый дом и перенос существующей основной метки на другой дом требуют 409:
`detail.code=building_binding_conflict`, `snapshot`, `confirmation_token`.
Snapshot перечисляет старую метку, прежний дом, целевой дом, версии и старую/новую позиции.
Повтор отправляется с `binding_confirmation`. HMAC привязан к актуальному snapshot и
операции, проверка повторяется под блокировками. Изменённый конфликт снова даёт 409.
`force=true` не существует.

Порядок записи: transaction advisory lock компании → отсортированные дома → метки.
Все изменения одной операции коммитятся вместе. UNIQUE остаётся последней защитой.
Освобождённая метка не удаляется: становится reference и сохраняет последнюю точку/стиль.
Прежний дом получает стандартное отображение. Повтор той же основной связи не требует
нового подтверждения; версия PATCH увеличивается предсказуемо.

Совместимость: старый `building_id` без роли означает справочную связь.
`sync_building_coordinates=false` принимается; `true` даёт контролируемый 422
`legacy_coordinate_sync_removed`, не создавая второй write path.
Локальные frontend-потребители обновлены. Внешним клиентам нужно перейти на явную роль.

## MapConnection

Отдельная таблица `map_connections`, не безымянный GeoJSON:

- Реальные FK на Building и составные `(company_id, marker_id)` FK на MapMarker.
- CHECK: ровно один FK на конец, разные типизированные концы, видимость/владелец.
- `medium=fiber|utp`, четыре статуса, положительное целое `fiber_count` либо Cat 5e/6/6A.
- До 498 внутренних WGS84-вершин, 2D, конечные числа. Поля другой среды отвергаются.
- Нулевая длина отвергается; одинаковая позиция разных точек не объединяет их.
- `version` и обязательный `expected_version` для изменения полного черновика линии.

Ссылка на основную метку нормализуется к Building; независимая точка остаётся MapMarker.
Концы геометрии читаются из текущих объектов SQL-запросом. Внутренние вершины сохраняются.
Нет materialized geometry/cache, который надо массово обновлять после перемещения.
Пересечение линий не создаёт соединение. Два кабеля между одинаковыми концами допустимы.
Удаление занятого конца блокируется; список раскрывает только доступные зависимости.
Смена visibility занятой точки и превращение занятой независимой точки в represents
блокируются до явного переназначения линий — сеть не переподключается молча.

`length_m` — геодезическая длина по карте (haversine, метры), не длина кабеля с запасами.
Без координат одного конца detail возвращает `geometry=null`, `position_missing=true`.

## API

Все маршруты требуют JWT, X-Company-Id и `addresses.read`; общие записи дополнительно
требуют `addresses.manage` на сервере, независимо от состояния кнопок.

```text
GET/POST       /api/v1/map/markers
GET/PATCH/DELETE /api/v1/map/markers/{id}
GET            /api/v1/map/buildings/{id}/marker
GET/POST       /api/v1/map/connections
GET/PATCH/DELETE /api/v1/map/connections/{id}
GET            /api/v1/map/endpoints?q=...&limit=20&offset=0
GET/POST       /api/v1/map/marker-styles
GET/PATCH/DELETE /api/v1/map/marker-styles/{id}
```

Метки/линии принимают полный viewport `west/south/east/north`.
Для списка зависимостей линий доступны `endpoint_kind=building|marker&endpoint_id=...`.
Концы в запросе — discriminated union `{kind:'building'|'marker', id:...}`;
ответ содержит также понятное имя и текущие координаты.
Стиль — `{name, appearance}`; PATCH добавляет `expected_version`.
Пресет хранит только оформление, максимум 200 на владельца/компанию.
Смена/удаление пресета не изменяет существующие метки.

Смешанный адресный поиск Stage 25.13/25.17.1 не переписан и сохраняет свой контракт.
Отдельный endpoint-picker ищет доступные дома и самостоятельные точки; primary-оформления
не дублируют дома в его результатах.

## SQL, индексы и ограничения масштаба

Контекст/владелец, partial UNIQUE основной связи и FK-индексы концов.
Viewport линий использует PostgreSQL `lseg ?# box` для каждого фактического сегмента,
включая линии с обоими внешними концами. PostGIS не требуется.
Отбор выполняется в PostgreSQL, не matching всех маршрутов в Python.
Текущий viewport меток учитывает CASE для канонической точки дома: индекс независимых
координат не объявляется ускорителем этого вычисляемого выражения.

Воспроизводимая fixture: 1000 точек / 500 линий / две внутренние вершины.
`EXPLAIN (ANALYZE, BUFFERS)`: метки 0,262 мс; линии viewport 2,369 мс;
зависимости конца 0,051 мс. Последний запрос реально использует BitmapOr индексов
source_marker_id/target_marker_id. На небольшой fixture PostgreSQL выбирает Seq Scan
для всего контекста — не отключали planner ради демонстрации индекса.
Полные планы: [query-plans.txt](verification/stage25.17.2/query-plans.txt).

```bash
python -m pytest -vv -s tests/authorization/test_map_query_plans.py
```

Первая версия не имеет пространственного индекса трассы: стоимость пересечения
пропорциональна доступным линиям и числу их вершин. Это проверено для указанной fixture,
не для миллионов сегментов. Лимиты: 5000 меток / 2000 линий на viewport; превышение —
явный 422 с предложением увеличить масштаб, не молчаливое обрезание.
Antimeridian viewport (west > east) не поддержан; карты используют текущие валидные bounds.
Записи графа сериализованы в рамках одной компании — сознательное упрощение первой версии.

## Безопасное обновление development database

Alembic не добавлен. `database/map_upgrade.py` — транзакционное, идемпотентное обновление.

1. Сделать обычный `pg_dump` базы и проверить возможность восстановления.
2. Перед новым backend выполнить dry-run новым кодом:

   ```bash
   docker compose run --rm --no-deps -v "$PWD/app:/srv/xarionix/app" api python -m database.map_upgrade --dry-run
   ```

3. Проверить `conflicts` и `unpositioned_buildings`. Несколько старых sync-меток одного
   дома не имеют случайного победителя. У дома без канонической точки автоматической
   основной связи тоже не будет.
4. Применить новый код: `docker compose up -d --build --no-deps --wait api`.
   Инициализация вызывает тот же upgrade; явный `--apply` доступен для обслуживания.
5. Проверить `docker compose exec -T api python -m database.map_upgrade --dry-run` и health.

Перед преобразованием создаётся постоянная `map_marker_legacy_backup` со всеми старыми
строками/позициями/оформлением. Старые обычные связи становятся reference. Только одиночный
явный sync при наличии канонической точки превращается в represents; конфликтующие
и нерасположенные сохраняют исходную независимую позицию. Таблицы не удаляются.
Резервная таблица не заменяет полный pg_dump. Для отката планировать остановку и
проверенное восстановление, не удалять новые таблицы произвольными SQL-командами.

Нужны права владельца существующих таблиц на ALTER/CREATE INDEX и CREATE TABLE/FK.
pg_trgm уже требовался адресному поиску; новые расширения не добавлены.
Локально dry-run нашёл 0 старых меток; обновление применено, повторный dry-run —
`upgrade_required=false`, API healthy. Postgres/Redis/map-proxy не пересоздавались.

## Проверки и файлы

Полный `pytest -vv`: 506 passed. Реальные PostgreSQL тесты подтверждают транзакции,
гонку первой привязки, UNIQUE/FK, rollback, stale confirmation, canonical coordinates,
JWT/company/ownership, private-концы, viewport, миграцию и прежний адресный поиск.
`docker compose config -q` успешен. Yandex API в нагрузочных тестах не использовался.

Изменены: `app/api/v1/map.py`, `app/core/map_markers.py`, `app/database/engine.py`,
`app/models/{__init__,map_markers}.py`, `app/repositories/map_markers.py`,
`app/schemas/map_markers.py`, `app/services/{addresses,building_coordinates,map_markers}.py`,
`tests/authorization/test_map_api.py`.
Добавлены: `app/core/map_domain.py`, `app/database/map_upgrade.py`,
`app/models/{map_connections,map_style_presets}.py`, `app/schemas/map_connections.py`,
`app/services/map_connections.py`, `tests/authorization/{test_map_graph_api,test_map_query_plans}.py`.

Рекомендуемый commit: `feat(map): add explicit house bindings, private points, connections and personal styles`.
Stage 25.14/26 не начинались.
