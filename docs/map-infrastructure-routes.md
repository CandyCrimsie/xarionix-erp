# Объекты и способы прокладки на кабельной трассе

Реализация от 28 октября 2026, продолжение `69dc838`. Существующий split не
заменён: его блокировки, проверки и транзакция обобщены для разрешённых узлов.
Адресная модель, RBAC, viewport SQL, поставщик тайлов и сетевой инвентарь не менялись.

## Типы и топология

Добавлены `fiber_box` (оптический бокс), `odf` (оптический кросс), `transition`
(точка перехода). Все прежние point types и идентификаторы иконок сохранены.

- **Вставить узел**: `splice`, `fiber_box`, `odf`, `network_node`, `cabinet`.
  Создаёт реальный конец двух соединений. Первый участок сохраняет ID исходной
  линии и получает следующую версию, второй — новый ID и версию 1.
- **Разместить вдоль трассы**: `chamber`, `pole`, `transition`, а также
  `fiber_box`, `network_node`, `cabinet` при явном выборе этой роли.
  Создаёт метку и привязку, но НЕ меняет концы, число соединений или топологию.
- Выбранная иконка не определяет топологию. Allowlist операции проверяется
  Pydantic и сервисом. Произвольные company/owner/visibility/coordinate поля
  внутри marker запрещены. Владение и видимость наследуются от трассы.

## API

Все операции используют прежние JWT, `X-Company-Id`, `addresses.read`,
`require_write`, `addresses.manage` для технической инфраструктуры.
Чужой private-объект не раскрывается даже администратору компании.

Общий снимок точки:

```json
{
  "expected_version": 3,
  "expected_geometry_token": "<64 hex из ответа соединения>",
  "segment_index": 1,
  "fraction": 0.37,
  "position": {"latitude": 55.58, "longitude": 38.25}
}
```

Позиция в примере условная. Нужна реальная точка Mercator-сегмента, не линейная
интерполяция широты. Действуют прежние допуск 5 см, точность БД 7 знаков,
минимум 1 м по трассе до каждого конца, предел 498 промежуточных вершин.

| POST endpoint | Дополнительные поля | Ответ |
| --- | --- | --- |
| `/api/v1/map/connections/{id}/split` | `marker: {name, point_type, ...appearance}` | 201 `{marker, connections:[first,second]}` |
| `/api/v1/map/connections/{id}/route-objects` | `marker`, необязательный `installation_after` | 201 `{marker,connection}` |
| `/api/v1/map/connections/{id}/installation-boundaries` | `installation_after`, `until: "end" / "next_vertex"` | 200 соединение |
| `/api/v1/map/connections/{id}/route-objects/{marker_id}/detach` | Только `expected_version`, `expected_geometry_token` | 200 `{marker,connection}` |

Старый split payload без `marker.point_type` по-прежнему создаёт муфту.
Контракты CRUD дополнены `installation_methods`, `route_objects` у соединения,
`route_attachment` у метки. Старые поля не переименованы.

## Устойчивые привязки

`map_route_objects` хранит company, marker, connection, snapshot геометрии,
индекс и долю сегмента. **Географический якорь — сохранённые координаты метки**,
а не индекс сегмента. Индекс — кэш только для соответствующего snapshot.

При правке геометрии фиксированная точка перепроецируется на новую полилинию.
Если она больше не лежит на ней либо новое положение неоднозначно на
самопересечении, возвращается `409 route_anchor_conflict`. Координаты не
подменяются автоматически. Подразделение сегмента с сохранением точки разрешено.

При split привязки явно распределяются между двумя участками по положению
вдоль выбранного маршрута (включая выбранную ветвь на пересечении). Географические
координаты сохраняются. Второй пересекающийся кабель не затрагивается.

Проверяются также перемещения концов через обычный marker/building API.
Привязанный объект нельзя незаметно переместить, перепривязать к дому или
изменить его тип/видимость. Имя и оформление редактируются как обычно.
Перед удалением трассы или изменением её видимости нужна явная отвязка.
Отвязка сохраняет самостоятельную метку в прежней точке. Явное удаление самой
метки удаляет её привязку через FK CASCADE; трасса остаётся.

Если импорт/прямой SQL обошёл защиту, карта возвращает `needs_attention`, а не
прячет метку и не переносит её. Отвязка доступна даже для утратившей геометрию линии.

## Способы прокладки

`map_connections.installation_methods` — JSONB-массив, одно значение на ребро
полной геометрии `[source, *vertices, target]`:

`unknown`, `aerial`, `duct`, `direct_buried`, `facade`, `indoor`.

Это характеристика прокладки, независимая от `medium` и `status`. Граница
добавляется как обычная геометрическая вершина, без фиктивного физического узла.
При split способ разрезанного сегмента переходит в оба новых участка.
Вставка вершины дублирует способ сегмента, удаление границы разных способов
требует явного выбора результата. Разворот трассы разворачивает массив способов.

CHECK проверяет тип JSONB, допустимые значения и длину `len(vertices)+1`.
`[]` — совместимое хранилище старых all-unknown записей, чтение разворачивает
его в полный массив. Старый клиент без поля не теряет известные способы при
изменении названия. Изменение геометрии такого кабеля без явного массива
отклоняется `409 installation_methods_required`.

## Транзакции

Компания advisory lock → строка трассы FOR UPDATE → упорядоченные блокировки
домов и маркеров концов → повторное чтение геометрии → проверки → изменения →
формирование ответа → единственный commit. Ошибка в любой части даёт rollback.
Placement и boundary также увеличивают версию, чтобы повторное сохранение или
конкурирующая операция не создавали дубликаты. Snapshot ловит перемещение конца
даже без смены версии линии. Проверка перемещения конца не берёт обратные
company/connection locks, избегая инверсии порядка блокировок.

## Безопасное обновление development database

Alembic не добавлен. `create_all()` НЕ используется как замена обновления CHECK.
Добавлен транзакционный idempotent upgrader:

```bash
cd app
python -m database.map_routes_upgrade --dry-run
python -m database.map_routes_upgrade --apply
```

Он обновляет `ck_map_markers_point_type`, добавляет `installation_methods` и
его CHECK, UNIQUE `(company_id,id)` у соединений и новую таблицу привязок с
company-composite FK и индексом `(company_id,connection_id)`. Старые строки,
геометрия и ID не переписываются и не удаляются. Нужны права владельца таблиц
на ALTER/CREATE. Перед обновлением существующей БД сделайте обычный backup.

Upgrader подключён и к инициализации API **до** `create_all()`, и к прежнему
`database.map_upgrade --apply`. DDL выполняется одной транзакцией с advisory lock
и `lock_timeout=5s`: при занятой БД запуск явно завершится ошибкой без частичной
схемы; повторите после завершения долгого писателя. Новая установка создаёт
сразу актуальную схему. Расширения PostgreSQL для этой доработки не нужны.

После обновления локальных исходников достаточно `docker compose up -d --build api`.
`pull` не собирает локальный код, `down` и удаление volumes не нужны.
Рабочая development database в ходе разработки не менялась.

## Проверки

`pytest -vv`: **552 passed** на Python 3.13, PostgreSQL 18.6, Redis 8 в
изолированных тестовых контейнерах. Включая прежние 22 split и 16 graph tests.
Новые 24 сценария проверяют все новые типы, пять типов split-узлов, mixed
methods, placement/detach, живые перемещения концов, перепривязку при split,
сохранение координат при редактировании оформления, rollback обеих операций,
гонку placement/boundary в независимых SQL-сессиях, JWT/private/company isolation,
CHECK напрямую в PostgreSQL и реальное обновление старой схемы без потери строк.
`docker compose config --quiet` и `git diff --check` проходят.

## Файлы backend

```text
app/api/v1/map.py
app/core/map_markers.py
app/core/map_routes.py                         # новые методы и якоря
app/database/engine.py
app/database/map_upgrade.py
app/database/map_routes_upgrade.py             # новая additive migration
app/main.py                                   # доменный конфликт из building API → 409
app/models/__init__.py
app/models/map_connections.py
app/models/map_markers.py
app/models/map_route_objects.py                # новая таблица
app/schemas/map_connections.py
app/schemas/map_markers.py
app/services/building_coordinates.py
app/services/map_connections.py
app/services/map_markers.py
app/services/map_route_objects.py
tests/authorization/test_map_routes_api.py
docs/map-connection-split.md
docs/map-infrastructure-routes.md
```

## Ограничения

Нет учёта сварок, кассет, портов, кабельного инвентаря или автоматического
слияния разделённых линий. Привязка одной метки относится к одной трассе;
совпадение координат не соединяет кабели. Изменение маршрута в стороне от
закреплённого объекта требует явного detach, затем нового размещения — без
скрытого переноса. Сохраняются ограничения Mercator и линии перемены дат.
Новые слои управления, кластеризация и PostGIS не добавлялись.
