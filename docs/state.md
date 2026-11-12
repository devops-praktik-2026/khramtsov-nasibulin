# Управление состоянием стенда — занятие 7, карточки 3.2–3.4

OpenTofu 1.10+ создаёт учебный стенд, хранит состояние в MinIO и отдаёт
готовый inventory. MinIO запускается отдельным Compose-проектом с томом
`praktikum-state-data`: `tofu destroy` не удаляет ни хранилище, ни его версии.
State содержит сведения о ресурсах и может содержать пароли. Это не резервная
копия данных PostgreSQL.

## Подготовить хранилище

Нужны Docker с Compose и Buildx, OpenTofu 1.10+, Python 3.11+ и SSH-ключ.
Все команды выполняются из корня репозитория, если не указано другое.
Порты 9000 и 9001 должны быть свободны. Хранилище слушает только loopback.

В PowerShell:

```powershell
.\tools\state\Start-MinIO.ps1
```

Скрипт запрашивает учебный пароль без отображения, задаёт
`AWS_ACCESS_KEY_ID` и `AWS_SECRET_ACCESS_KEY` **в текущем терминале**,
собирает MinIO, создаёт bucket `praktikum-state` и включает версионирование.
В другом терминале задайте те же значения заново. Для повторного запуска
используйте прежний пароль: скрипт не является средством ротации доступов.

В Bash на macOS/Linux:

```bash
export AWS_ACCESS_KEY_ID=praktikum
read -rsp 'Пароль MinIO: ' AWS_SECRET_ACCESS_KEY; printf '\n'
export AWS_SECRET_ACCESS_KEY
make state-up
```

Образ собирается из закреплённых исходных релизов MinIO и `mc`, поэтому
первая сборка требует интернета и занимает несколько минут. `init` можно
повторять: существующий bucket сохраняется. Консоль доступна по
<http://127.0.0.1:9001>, S3 API — по <http://127.0.0.1:9000>.
Консоль некоторых версий MinIO не поддерживает администрирование bucket;
создание и включение версий выполняет контейнер `init` через `mc`.

## Сохранить прежнее состояние и перенести его

Если стенд уже существует, работайте в **том же** `infra/terraform` и сохраните
прежние значения переменных, особенно `db_password`. Иначе план будет менять
инфраструктуру одновременно с переносом состояния. Завершите другие операции
OpenTofu и скопируйте `terraform.tfstate` в защищённый каталог **вне Git**.
Резервные `terraform.tfstate.backup` также храните вне репозитория.

Пароль базы больше не имеет значения по умолчанию. Передайте его через
`TF_VAR_db_password` или локальный игнорируемый `*.tfvars`.
Для прежнего стенда это его прежний пароль, для нового — выбранный вами пароль.
OpenTofu сам не загружает `.env`.

В PowerShell для ввода пароля без записи в историю команд:

```powershell
$secret = Read-Host 'Пароль базы' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $env:TF_VAR_db_password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
cd infra/terraform
tofu fmt -check
tofu init -migrate-state
# Подтвердите копирование существующего состояния.
tofu validate
tofu plan
```

В Bash пароль задаётся через `read -rsp 'Пароль базы: ' TF_VAR_db_password`,
затем `export TF_VAR_db_password`; команды OpenTofu те же.
При первом создании без прежнего state достаточно `tofu init`.
На macOS при недоступном `/var/run/docker.sock` задайте
`export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"`.

После миграции план не должен предлагать заново создать существующие ресурсы.
Допустимо добавление нового output. Если предлагается создать весь стенд,
остановитесь и проверьте backend, bucket, key, workspace и резервную копию.
Не применяйте такой план к существующему стенду.

В MinIO появится `stand/terraform.tfstate`. В конфигурации backend нет паролей;
они поступают через AWS-переменные. Файл `.terraform/terraform.tfstate` после
`init` содержит локальные метаданные backend, а рабочий state лежит в S3.

## Получить inventory и настроить серверы

После добавления output выполните `tofu apply`, даже если ресурсы не меняются.
Inventory строится по созданным серверам и их опубликованным SSH-портам.

```powershell
# В infra/terraform
.\Write-Inventory.ps1
```

Или из корня на любой системе: `make inventory` / `python scripts/write_inventory.py`.
Получится `infra/ansible/inventory.ini` в UTF-8 без BOM. При ошибке OpenTofu
старый файл остаётся на месте. Не используйте `>` в Windows PowerShell 5.1:
его кодировка по умолчанию — UTF-16.

По умолчанию `ansible_host=host.docker.internal` рассчитан на Ansible
**в контейнере**. Если запускаете Ansible непосредственно на macOS/Linux
по [инструкции занятия 6](ansible.md), задайте `ansible_host = "127.0.0.1"`
в локальном `terraform.tfvars`, выполните `tofu apply` и `make inventory`.
Адреса и порты серверов вручную в inventory не переносите.

Для контейнера Ansible:

```bash
docker build -t praktikum-ansible:lesson7 tools/ansible
# Выполняется из корня; закрытый ключ монтируется только во время запуска.
docker run --rm -it --add-host host.docker.internal:host-gateway \
  -v "$PWD:/work" -v "$HOME/.ssh:/root/.ssh:ro" \
  -e ANSIBLE_PRIVATE_KEY_FILE=/root/.ssh/id_ed25519 \
  praktikum-ansible:lesson7 bash
```

Эквивалент запуска из PowerShell:

```powershell
docker build -t praktikum-ansible:lesson7 tools/ansible
docker run --rm -it --add-host host.docker.internal:host-gateway `
  --mount "type=bind,source=$($PWD.Path),target=/work" `
  --mount "type=bind,source=$HOME/.ssh,target=/root/.ssh,readonly" `
  -e ANSIBLE_PRIVATE_KEY_FILE=/root/.ssh/id_ed25519 `
  praktikum-ansible:lesson7 bash
```

Если ключ называется иначе, замените только `ANSIBLE_PRIVATE_KEY_FILE`.
Ключ с парольной фразой загрузите в `ssh-agent` внутри этого контейнера.
Внутри контейнера:

```bash
python -m build --wheel --outdir dist services/orders
# Только при первой настройке, не затирайте существующие параметры:
cp -n infra/ansible/vars.example.yml infra/ansible/vars.local.yml
# В vars.local.yml укажите открытые ключи участников (см. ansible.md).
ansible-inventory -i infra/ansible/inventory.ini --graph
ansible -i infra/ansible/inventory.ini app -m wait_for_connection -a 'timeout=60'
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/site.yml -e @infra/ansible/vars.local.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/site.yml -e @infra/ansible/vars.local.yml
```

На немедленном повторе ожидается `changed=0`, `failed=0`, `unreachable=0`.
Закрытый ключ не входит ни в build context `tools/ansible`, ни в образ.
Проверка `/health` и ограничения сценария приложения описаны в `ansible.md`.

## Проверить блокировку

В двух терминалах одной машины задайте одинаковые AWS-переменные и переменные
стенда; откройте один и тот же `infra/terraform`.

1. В первом выполните `tofu apply -refresh-only` и оставьте подтверждение открытым.
2. Во втором: `tofu plan -lock-timeout=5s`. Ожидается ошибка получения блокировки.
3. В первом ответьте `no`, затем повторите `plan` во втором. Он должен завершиться.

Если refresh-only не просит подтверждения, временно создайте `lock-probe.tf`
с `output "lock_probe" { value = "lesson7" }`, выполните обычный `tofu apply`
и оставьте подтверждение открытым. После опыта ответьте `no` и удалите
**только этот временный файл**. Он не коммитится и не требует применения.
Не используйте `force-unlock`, пока не убедились, что владелец блокировки завершился.

Блокировка защищает один объект состояния: должны совпадать endpoint,
bucket, key и workspace. Это опыт двух процессов с одним Docker.
На другом компьютере напарник использует собственный MinIO/state для своего
Docker. Одинаковый `127.0.0.1` на двух машинах не означает общее хранилище.
Для настоящей совместной работы нужны общий защищённый backend и одна
целевая инфраструктура; локальный MinIO не обеспечивает отказоустойчивость.

## Восстановить стенд

Сохраните нужные данные PostgreSQL отдельно. Проверьте `tofu plan -destroy`,
затем выполните `tofu destroy`, `tofu apply`, генерацию inventory и Ansible.
Повторите Ansible и проверьте `/health` обоих серверов. Удаление тома
PostgreSQL означает потерю данных базы, даже если сохранены все версии state.

Контейнер и том MinIO оставьте работающими. Для обычной остановки хранилища
можно использовать `docker compose -f tools/state/compose.yaml stop`,
для запуска — `make state-up` с прежними доступами. Не удаляйте его том.
В PR укажите результаты восстановления и опыта блокировки; state не прикладывайте.
Напарник воспроизводит стенд у себя с отдельным состоянием и подтверждает результат.

## Код, параметры и секреты

- В Git: описание ресурсов, сценарии, `.env.example` с пустыми секретами,
  `vars.example.yml` с образцами открытых ключей и lock-файл провайдера.
- Вне Git: `.env*`, локальные tfvars/YAML/backend-файлы, inventory, state и
  резервные копии, закрытые SSH-ключи. Не добавляйте их через `git add -f`.
- Actions публикует образ через `${{ secrets.GITHUB_TOKEN }}` с правом
  `packages: write`; публикация ждёт в том числе успешного поиска секретов.
  Дополнительные доступы задаются в Settings → Secrets and variables → Actions,
  а не в workflow, build args или открытых переменных. Локальный MinIO
  недоступен облачному runner и для сборки приложения не нужен.

Проверьте `git ls-files .env` (пусто), `make test-infra`, `make lint`, `make test`.
CI запускает `tofu fmt -check`, `init -backend=false`, `validate` и тесты inventory.
Gitleaks в Actions проверяет всю историю (`fetch-depth: 0`, `gitleaks git . --redact`).
При утечке сначала отзовите доступ, затем согласуйте очистку истории;
простое удаление файла не удаляет его из старых коммитов.

Настройка backend и блокировки сверена с
[документацией OpenTofu S3](https://opentofu.org/docs/language/settings/backends/s3/).
Исходные релизы: [MinIO](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)
и [mc](https://github.com/minio/mc/releases/tag/RELEASE.2025-08-13T08-35-41Z).
