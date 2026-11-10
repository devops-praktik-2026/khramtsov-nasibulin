# Настройка серверов — занятие 6, карточка 3.1

OpenTofu создаёт сеть, базу и два сервера в Docker. Ansible запускается
напрямую из Python-окружения и подключается к серверам по SSH под `deploy`.
`become: true` позволяет выполнять задачи через sudo.

Роль `base` устанавливает системные пакеты, создаёт `/opt/orders` и добавляет
открытые ключи участников, сохраняя существующие. Роль `app` копирует wheel,
устанавливает его в `/opt/orders/venv`, проверяет версию, формирует `.env`
и описание процесса Supervisor. Изменение пакета или шаблонов вызывает
обработчик перезапуска. `flush_handlers` применяет изменения до проверки `/health`.
Структура ролей сверена с комплектом `tasks/Занятие_6/examples/lesson6`.

## Подготовка

Нужны Python 3.12+, модуль venv, OpenSSH, Docker с Buildx и OpenTofu 1.10+.
Проверьте инструменты из корня проекта:

```bash
python3 --version
docker version
docker buildx ls
tofu version
```

## SSH-ключи и стенд

Используйте существующий ключ занятия 5. Закрытый ключ храните в `~/.ssh`
Unix-среды, с правами `0600`; его открытая часть должна соответствовать
`ssh_public_key_path` в локальном tfvars. Если ключ уже находится там:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
export ANSIBLE_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519"
```

Для другого имени укажите фактический Unix-путь. Например, ранее использованный
ключ стенда можно скопировать из `.local/ssh/stand_key` в `~/.ssh/stand_key`
и задать `ANSIBLE_PRIVATE_KEY_FILE="$HOME/.ssh/stand_key"`.
Для ключа с парольной фразой:

```bash
eval "$(ssh-agent -s)"
ssh-add "$ANSIBLE_PRIVATE_KEY_FILE"
```

Создайте или проверьте стенд:

```bash
cd infra/terraform
tofu init
tofu plan
tofu apply
tofu output servers
cd ../..
```

## Python-окружение и пакет приложения

```bash
python3 -m venv .venv-ansible
. .venv-ansible/bin/activate
python -m pip install -r tools/ansible/requirements.txt
python -m build --wheel --outdir dist services/orders
cp infra/ansible/inventory.example.ini infra/ansible/inventory.ini
cp infra/ansible/vars.example.yml infra/ansible/vars.local.yml
```

`cp` выполняйте при первой настройке, чтобы не затереть свои локальные параметры.
В `vars.local.yml` замените образцы **открытыми** ключами обоих участников.
При индивидуальной работе оставьте один ключ. Закрытые ключи туда не добавляются.
Inventory, локальные переменные, окружение и wheel исключены из Git.
`orders_version` по умолчанию соответствует `0.1.0` в
`services/orders/pyproject.toml`; при смене версии обновите переменную.

Коллекции `ansible.posix` и `community.general` входят в пакет Ansible.
Их список также есть в `infra/ansible/requirements.yml` для отдельной установки
через `ansible-galaxy collection install -r requirements.yml` из `infra/ansible`.

## Проверка и установка

В том же терминале с активным окружением:

```bash
cd infra/ansible
ansible-inventory -i inventory.ini --graph
ansible -i inventory.ini app -m wait_for_connection -a 'timeout=60'
ansible -i inventory.ini app -m ping
ansible-playbook -i inventory.ini site.yml -e @vars.local.yml --syntax-check
ansible-playbook -i inventory.ini site.yml -e @vars.local.yml
ansible-playbook -i inventory.ini site.yml -e @vars.local.yml
```

На повторе ожидаются `changed=0`, `failed=0`, `unreachable=0` у обоих серверов.
Модули сравнивают фактическое состояние с требуемым и меняют только отличия.
Кеш apt действителен час: после его истечения обновление списка пакетов допустимо.
При изменении wheel той же версии пакет переустанавливается.
Для статической проверки используйте `--syntax-check`: полный первый запуск
в режиме `--check` не поддерживается.

Из Unix-терминала проверьте опубликованные порты и Supervisor:

```bash
curl --fail http://127.0.0.1:8101/health
curl --fail http://127.0.0.1:8102/health
ssh -i "$ANSIBLE_PRIVATE_KEY_FILE" -p 2201 deploy@127.0.0.1 'sudo supervisorctl status orders'
ssh -i "$ANSIBLE_PRIVATE_KEY_FILE" -p 2202 deploy@127.0.0.1 'sudo supervisorctl status orders'
```

Оба ответа должны содержать `{"status":"ok","service":"orders"}`,
Supervisor должен показать `RUNNING`. Ansible также проверяет эти поля внутри
каждого сервера по `127.0.0.1:8000` с ожиданием запуска.

## Адреса и границы проверки

| Откуда | Куда | Адрес |
| --- | --- | --- |
| Unix-терминал, Ansible | SSH серверов | `127.0.0.1:2201`, `127.0.0.1:2202` |
| Unix-терминал | orders | `127.0.0.1:8101`, `127.0.0.1:8102` |
| Задача uri на сервере | собственный orders | `127.0.0.1:8000` |

Docker должен быть доступен локально: inventory рассчитан на порты этой машины.
`localhost` внутри серверного контейнера означает сам сервер.
`orders_accounts_url` задаёт адрес accounts **с точки зрения сервера**.
Его исходное значение `http://host.docker.internal:8001` подходит для Docker Desktop.
На Linux с Docker Engine задайте в `vars.local.yml` доступный серверу адрес
accounts: например, сетевое имя контейнера в общей Docker-сети или адрес хоста.
Это отдельное сетевое соединение; адрес SSH в inventory на него не влияет.
`/health` не требует accounts и базы; миграции и сквозное создание заказов
рассматриваются отдельно.

## Проверка восстановления

Сохраните необходимые данные базы: `destroy` удаляет и том PostgreSQL.
В `infra/terraform` выполните `tofu plan -destroy`, проверьте состав,
затем `tofu destroy` и `tofu apply`. Повторите настройку и немедленный повтор
Ansible, проверьте оба внешних `/health`. Сценарий должен работать на чистых
машинах без ручной настройки.

## Диагностика

- `UNREACHABLE`: проверьте `docker ps`, `tofu output servers`, адреса и порты
  в inventory, значение `ANSIBLE_PRIVATE_KEY_FILE` и права ключа.
- `BACKOFF`: выполните `sudo supervisorctl tail orders stderr` на сервере.
- `Permission denied` от supervisorctl: используйте `sudo`.

Поведение обработчика описано в
[документации community.general.supervisorctl](https://docs.ansible.com/projects/ansible/latest/collections/community/general/supervisorctl_module.html).

## Результаты проверки ролей — 10 ноября 2026

Роли проверены с Ansible 14.6.0 и существующим ключом стенда
`.local/ssh/stand_key`. Результаты ниже относятся к проверке ролей,
выполненной до изменения способа запуска Ansible.

| Проверка | server-1 | server-2 |
| --- | --- | --- |
| SSH и Ansible ping | pong | pong |
| Первая установка | ok=14, changed=6, failed=0 | ok=14, changed=6, failed=0 |
| Немедленный повтор | ok=13, changed=0, failed=0 | ok=13, changed=0, failed=0 |
| Установка после полного пересоздания | ok=14, changed=6, failed=0 | ok=14, changed=6, failed=0 |
| Повтор после пересоздания | ok=13, changed=0, failed=0 | ok=13, changed=0, failed=0 |
| Supervisor после восстановления | orders RUNNING | orders RUNNING |
| Внешний /health после восстановления | status=ok, service=orders | status=ok, service=orders |

Во всех запусках `unreachable=0`. Проверка синтаксиса прошла.
OpenTofu удалил 7 ресурсов и создал 7 заново; имена и порты сохранились.
Перед удалением сохранён дамп учебной базы `.local/lesson6-before.dump`.
После восстановления база создана заново без прежних данных.

Журналы сохранены локально в `.local/lesson6/`: `initial.log`, `repeat.log`,
`destroy-plan.log`, `destroy.log`, `recreate-plan.log`, `recreate.log`,
`recreated-initial.log`, `recreated-repeat.log`. Секретные параметры `.env`
скрыты через `no_log`; закрытый ключ в журналы не выводится.
Дополнительно прошли 67 тестов приложения (покрытие 97,12%),
`ruff check`, `ruff format --check` и `git diff --check`.

Проверка выполнена с одним открытым ключом. Для парной сдачи добавьте ключ
напарника в `deploy_public_keys` файла `vars.local.yml` и повторите запуск.
Проверку и рецензию напарник выполняет самостоятельно.
Для PR: заголовок `3.1 Настройка серверов Ansible`, связь `Closes #24`.
