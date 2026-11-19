# Выпуск и восстановление orders

## Подготовить и опубликовать версию

Номер выпуска задаёт `version` в `services/orders/pyproject.toml`. Сначала
напарник принимает PR в `main`. Для двух выпусков из этого PR выберите
**Create a merge commit** или **Rebase and merge**, чтобы в истории остались
оба коммита с исходниками. При rebase берите новые SHA из `origin/main`.
У каждого тега должен быть свой коммит с соответствующей версией и
`.github/workflows/release.yml`.

Из корня репозитория после слияния выполните для каждой версии по очереди.
Укажите SHA принятого коммита с нужным номером. В ветке этого PR это
`ec015f9` для 0.1.0 и `0523a5b` для 0.2.0.

```bash
git fetch origin main --tags
tag=v0.1.0
read -rp 'SHA коммита выпуска из main: ' commit
git merge-base --is-ancestor "$commit" origin/main &&
  git show "${commit}:services/orders/pyproject.toml" |
  python3 -c 'import sys,tomllib; assert "v" + tomllib.load(sys.stdin.buffer)["project"]["version"] == sys.argv[1]' "$tag" &&
  git tag "$tag" "$commit" && git push origin "refs/tags/$tag"
```

Workflow сверяет номер, собирает wheel, запускает тесты на установленном пакете
и публикует этот же файл вместе с `SHA256SUMS` в GitHub Releases. Для следующего
выпуска используйте `tag=v0.2.0` и SHA второй версии. Состояние выпуска видно
в Actions и по `gh release view "$tag"`.

## Установить версию на два сервера

Нужны подготовленный inventory занятия 7, доступ по SSH и отдельная учебная
база orders. Для PostgreSQL используйте отдельную БД с собственной таблицей
`alembic_version`. Оба сервера должны получать один и тот же `orders_database_url`.
Укажите его и открытые ключи в игнорируемом `infra/ansible/vars.local.yml`.
Сценарий автоматически читает этот файл. Если Ansible
запускается в контейнере, адрес базы должен быть доступен с серверов стенда.
Перенос уже существующих заказов в другую БД требует переноса самих данных.

Следующие команды выполняются из `infra/ansible` на контроллере с Bash и
Ansible. Откройте `SHA256SUMS` в нужном GitHub Release и скопируйте 64
шестнадцатеричных знака из строки с именем устанавливаемого wheel.

```bash
repo=devops-praktik-2026/khramtsov-nasibulin
tag=v0.1.0
read -rp "SHA256 orders-${tag#v}-py3-none-any.whl: " checksum
ansible-playbook -i inventory.ini site.yml \
  -e "version=$tag" -e "release_repository=$repo" -e "release_checksum=sha256:$checksum"
```

Для установки 0.2.0 повторите блок с `tag=v0.2.0`. При повторе с теми же
параметрами у обоих серверов в итогах Ansible ожидается `changed=0`.
Supervisor запускает процесс через `/opt/orders/current/venv/bin/uvicorn`.
После переключения Ansible проверяет HTTP 200, `status=ok` и номер пакета.
Если первый сервер не прошёл проверку, второй остаётся на прежней версии.

С машины, где OpenTofu опубликовал порты по умолчанию, опросите оба сервера.

```bash
for port in 8101 8102; do curl -fsS "http://127.0.0.1:$port/health" && echo; done
```

Ответ каждой машины содержит, например, `{"status":"ok","service":"orders","version":"0.2.0"}`.
На контроллере проверьте ссылку, процесс и последние ошибки на обоих серверах.

```bash
ansible -i inventory.ini app -a 'readlink -f /opt/orders/current'
ansible -i inventory.ini app -b -a 'supervisorctl status orders'
ansible -i inventory.ini app -b -a 'supervisorctl tail orders stderr'
```

## Вернуть предыдущую версию

Если 0.1.0 уже успешно работала на этих серверах, для возврата достаточно
одной команды. Она использует сохранённые окружения. После завершения
проверьте оба внешних `/health` и чтение существующего заказа.

```bash
time ansible-playbook -i inventory.ini site.yml -e version=v0.1.0
```

## Сохранить базу и проверить миграцию

Перед обновлением сохраните архив общей PostgreSQL вне стенда. Из доверенного
терминала задайте обычные переменные клиента PostgreSQL для базы orders
(`PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`). Получите пароль через
`.pgpass` или интерактивный запрос клиента. Имя архива должно быть новым.

```bash
umask 077
backup="orders-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump -Fc -f "$backup" "$PGDATABASE" && pg_restore --list "$backup"
```

Проверьте архив восстановлением в отдельную пустую БД и сверкой числа заказов
и нескольких известных записей. При установке нового кода Ansible запускает
миграцию из его окружения до переключения первого сервера. Версия 0.2.0 добавляет
необязательное поле `orders.customer_note`. Старые записи получают `NULL`.
Код 0.1.0 может читать и создавать заказы на новой схеме.

Возврат только кода оставляет новую схему и заметки в базе. Для отдельной
проверки обратной миграции используйте восстановленную копию БД и окружение
**0.2.0**. Сначала проверьте `SELECT count(*) FROM orders WHERE customer_note IS NOT NULL`.
Команда ниже удаляет столбец вместе с его значениями. Сохраните нужные
заметки отдельно и подтвердите восстановление из архива до выполнения.

```bash
# На машине с установленной 0.2.0. Введите URL только восстановленной копии.
read -rsp 'DATABASE_URL копии: ' DATABASE_URL; echo
export DATABASE_URL
/opt/orders/releases/0.2.0/venv/bin/orders-migrate current
/opt/orders/releases/0.2.0/venv/bin/orders-migrate downgrade 483fb1e80029
```

## Найти и устранить отказ

### SHA256 не совпала при установке

Ansible останавливается на загрузке wheel. Проверьте оба `/health` и
`readlink -f /opt/orders/current`. Действующая версия должна по-прежнему
обслуживать заказы. Сверьте тег, имя wheel и строку из `SHA256SUMS` одного
GitHub Release. Повторите первую установку с проверенной суммой. Если при
правильной сумме ошибка повторяется, проверьте источник пакета.

### Supervisor показывает STOPPED

Если `curl` не получает ответ от одного порта, сравните его со вторым.
Посмотрите `supervisorctl status orders` и конец stderr этого сервера.
`STOPPED` после команды остановки означает, что Supervisor ждёт запуска.
Запустите playbook с последней рабочей версией, затем проверьте оба порта и
прочитайте известный заказ через `GET /orders/{id}`.

### Orders завершается при запуске

Если `supervisorctl status orders` показывает `BACKOFF` или `FATAL`,
посмотрите последнюю ошибку в `supervisorctl tail orders stderr`. В учебном
случае Uvicorn указывает на неизвестный параметр команды запуска.
Сравните строку `command=` в `/etc/supervisor/conf.d/orders.conf` с
`infra/ansible/roles/app/templates/orders.conf.j2`. Если параметр появился
на самом сервере, запуск playbook восстановит шаблон и применит его через
Supervisor. Если ошибка находится в репозитории, исправьте шаблон через PR
или запустите рабочую версию сценария. Проверьте состояние `RUNNING`, оба
ответа `/health` и чтение заказа.

### Повторить упражнение

Скрипт создаёт отдельные контейнеры двух SSH-серверов, PostgreSQL и контроллера.
Он вызывает роль через SSH, сохраняет заказ до миграции и сверяет данные
после возврата. Готовые wheel передаются ему файлами. Таким способом проверяются
оба кандидата до публикации тегов. Запускайте из корня репозитория с Docker
Compose, OpenSSH и Python 3.11+. Следующие команды используют исходники
двух коммитов PR. После публикации вместо SHA можно указать теги.

```bash
work=$(mktemp -d)
mkdir "$work/src-01" "$work/src-02"
git archive ec015f9 services/orders | tar -x -C "$work/src-01"
git archive 0523a5b services/orders | tar -x -C "$work/src-02"
python3 -m venv "$work/build-env"
"$work/build-env/bin/python" -m pip install build
"$work/build-env/bin/python" scripts/build_release.py --tag v0.1.0 \
  --source "$work/src-01/services/orders" --outdir "$work/old"
"$work/build-env/bin/python" scripts/build_release.py --tag v0.2.0 \
  --source "$work/src-02/services/orders" --outdir "$work/new"
REHEARSAL_REPORT="$work/report.md" bash tests/release/rehearse.sh \
  "$work"/old/*.whl "$work"/new/*.whl
```

При повторении с напарником выберите один из трёх случаев. Тот, кто дежурит,
получает только симптом и инструкцию. В комментарии к PR запишите наблюдаемую
ошибку, показания обоих `/health` после исправления и фактическое время.
