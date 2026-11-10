# Ansible в Unix-среде

Все команды выполняются в Unix-терминале.
Нужны Python 3.12+, Docker с Buildx, OpenTofu 1.10+ и OpenSSH.

Из корня репозитория:

```bash
python3 -m venv .venv-ansible
. .venv-ansible/bin/activate
python -m pip install -r tools/ansible/requirements.txt
python -m build --wheel --outdir dist services/orders
cp infra/ansible/inventory.example.ini infra/ansible/inventory.ini
cp infra/ansible/vars.example.yml infra/ansible/vars.local.yml
```

В `vars.local.yml` укажите открытые ключи участников. Затем:

```bash
export ANSIBLE_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519"
cd infra/ansible
ansible -i inventory.ini app -m ping
ansible-playbook -i inventory.ini site.yml -e @vars.local.yml --syntax-check
ansible-playbook -i inventory.ini site.yml -e @vars.local.yml
ansible-playbook -i inventory.ini site.yml -e @vars.local.yml
```

Ansible подключается к опубликованным SSH-портам `127.0.0.1:2201/2202`.
Коллекции из `infra/ansible/requirements.yml` включены в пакет `ansible`.
Подготовка ключей и проверки: [../../docs/ansible.md](../../docs/ansible.md).
