# XarionixERP

**XarionixERP** — это комплексное программное решение, которое объединяет ключевые бизнес-процессы компании в единую информационную среду.

## Границы доступа к адресному каталогу

`AddressType`, `AddressObject`, `Building` и `Entrance` образуют общий физический
каталог установки. Право `addresses.manage @ COMPANY` в текущем контракте
разрешает изменять этот глобальный каталог из выбранного company context.

`Location` относится к конкретной компании. Получение и изменение помещений,
технических описаний и связанных с ними данных всегда ограничивается текущим
`X-Company-Id`.

## Поиск адресов

Интеллектуальный поиск использует PostgreSQL-расширение `pg_trgm`. При запуске
API выполняется идемпотентная команда `CREATE EXTENSION IF NOT EXISTS pg_trgm`
до создания таблиц. Пользователь PostgreSQL должен быть владельцем базы либо
иметь право `CREATE` в ней; в стандартном `docker-compose.yml` база создаётся
этим же пользователем. Если политика production-базы запрещает это право,
администратор должен один раз выполнить команду от привилегированной роли.

Поиск выполняется непосредственно в PostgreSQL поверх существующего recursive
CTE. Номер дома, корпус и строение сравниваются точно; нечёткое сопоставление
применяется только к текстовым токенам длиной не менее пяти символов.

Воспроизводимый план для 105 000 тестовых зданий можно получить после запуска
тестового PostgreSQL:

```bash
docker exec -i xarionix_postgres_test \
  psql -U xarionix_test -d xarionix_test \
  < tests/performance/address_search_explain.sql
```

Скрипт сравнивает прежний contains-only запрос с новым структурированным
поиском через `EXPLAIN (ANALYZE, BUFFERS)` и использует только временные таблицы
в откатываемой транзакции.

## Тесты

Для локального запуска поднимите изолированные PostgreSQL и Redis, установите
зависимости и запустите `pytest`:

```bash
docker compose -f docker-compose.test.yml up -d
python -m pip install -r requirements-dev.txt
python -m pytest
docker compose -f docker-compose.test.yml down
```

По умолчанию тесты подключаются к PostgreSQL на `127.0.0.1:55432` и Redis на
`127.0.0.1:56379`. Для CI адреса можно переопределить переменными
`TEST_POSTGRES_*`, `TEST_REDIS_*` или полной строкой `TEST_DATABASE_URL`.

GitLab CI описан в `.gitlab-ci.yml`: job `python-tests` запускает весь набор
тестов с отдельными service-контейнерами PostgreSQL и Redis и публикует JUnit
отчёт в интерфейсе GitLab.

## Карта адресов и Yandex Tiles API

Картографическая интеграция состоит из трёх изолированных частей:

1. FastAPI проверяет JWT, `X-Company-Id` и `addresses.read`, выдаёт
   краткоживущую подписанную ссылку `/api/v1/map/session` и возвращает GeoJSON
   зданий только для текущего viewport через `/api/v1/map/buildings`.
2. Браузер загружает MapLibre динамически при открытии карты. Ключ Yandex API
   в JavaScript, HTML и ответах FastAPI отсутствует.
3. Отдельный Nginx-контейнер `map-proxy` проверяет подпись и координаты тайла,
   читает дисковый cache и только при cache miss обращается к фиксированному
   origin `tiles.api-maps.yandex.ru`. Общий limiter применяется после cache
   lookup и по умолчанию ограничивает весь proxy значением 28 RPS.

Для включения карты задайте одинаковый `MAP_TILES_SIGNING_SECRET` длиной не
менее 32 символов для API и proxy, добавьте `YANDEX_TILES_API_KEY`, установите
`MAP_TILES_ENABLED=true`, затем запустите инфраструктуру:

```bash
docker compose up -d --build
```

Без ключа proxy завершается с явной ошибкой конфигурации, а endpoint сессии
карты возвращает понятный HTTP 503. Если карта временно не нужна, остальные
сервисы можно запустить отдельно:

```bash
docker compose up -d --build api postgres redis
```

Порт proxy по умолчанию доступен только на
`127.0.0.1:8088`; Angular dev-server пересылает туда `/map/**`.

Настройки cache по умолчанию: 2 ГБ, TTL 12 часов, `inactive=7d`. Cache хранится
в named volume `map_tiles_cache`. В access log proxy записывается только path:
API key, подпись и query string не журналируются. Смените signing secret, чтобы
немедленно инвалидировать все ранее выданные browser permissions.

Новые установки получают частичный индекс
`ix_buildings_map_coordinates (longitude, latitude)` автоматически при
создании таблиц. Поскольку Alembic до стабильного релиза не используется, для
существующей development database создайте индекс вручную без долгой блокировки
записи:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_buildings_map_coordinates
ON buildings (longitude, latitude)
WHERE longitude IS NOT NULL AND latitude IS NOT NULL;
```

Сравнить план bbox-запроса на 550 000 строк до и после индекса можно командой:

```bash
docker exec -i xarionix_postgres_test \
  psql -U xarionix_test -d xarionix_test \
  < tests/performance/map_buildings_explain.sql
```

Проверка proxy использует локальный HTTPS mock origin, проверяет подпись,
валидацию `z/x/y`, cache HIT, cache lock, отсутствие секретов в логах и 250
параллельных cache misses:

```bash
infrastructure/map-proxy/tests/run-proxy-tests.sh
```

Перед production-включением нужно подтвердить подходящий тариф и лицензионные
условия Yandex Maps для закрытой ERP. Текущие общие бесплатные условия требуют
открытого бесплатного доступа к приложению; 12-часовой cache технически
является временным, но его допустимость и коммерческое использование должны
быть подтверждены условиями вашего тарифа. В UI нельзя скрывать или перекрывать
логотип Яндекса, ссылку «Открыть в Картах» и ссылку на условия использования.
