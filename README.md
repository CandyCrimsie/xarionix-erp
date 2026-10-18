# XarionixERP

**XarionixERP** — это комплексное программное решение, которое объединяет ключевые бизнес-процессы компании в единую информационную среду.

## Границы доступа к адресному каталогу

`AddressType`, `AddressObject`, `Building` и `Entrance` образуют общий физический
каталог установки. Право `addresses.manage @ COMPANY` в текущем контракте
разрешает изменять этот глобальный каталог из выбранного company context.

`Location` относится к конкретной компании. Получение и изменение помещений,
технических описаний и связанных с ними данных всегда ограничивается текущим
`X-Company-Id`.

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
