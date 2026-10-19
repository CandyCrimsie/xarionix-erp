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
