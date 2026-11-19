#!/usr/bin/env bash
# bash tests/release/rehearse.sh <wheel 0.1.0> <candidate wheel>
set -euo pipefail

if [[ $# != 2 ]]; then
    echo "Usage: $0 orders-0.1.0-py3-none-any.whl orders-X.Y.Z-py3-none-any.whl" >&2
    exit 2
fi
candidate_pattern='^orders-([0-9]+\.[0-9]+\.[0-9]+)-py3-none-any\.whl$'
if [[ ! -f $1 || ${1##*/} != orders-0.1.0-py3-none-any.whl ||
      ! -f $2 || ! ${2##*/} =~ $candidate_pattern ]]; then
    echo "Expected the baseline wheel and a versioned candidate wheel." >&2
    exit 2
fi
candidate=${BASH_REMATCH[1]}
[[ $candidate != 0.1.0 ]] || { echo "The candidate must differ from 0.1.0." >&2; exit 2; }

repo=$(cd "$(dirname "$0")/../.." && pwd)
REHEARSAL_DIR=$(mktemp -d "${TMPDIR:-/tmp}/orders-drill.XXXXXXXX")
COMPOSE_PROJECT_NAME=orders-drill-$(python3 -c 'from uuid import uuid4; print(uuid4().hex)')
REHEARSAL_DB_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
export REHEARSAL_DIR REHEARSAL_DB_PASSWORD COMPOSE_PROJECT_NAME
export COMPOSE_FILE="$repo/tests/release/compose.yaml"
built_images=()
started=false
cleanup() {
    if [[ $started == true ]]; then
        docker compose down --volumes --timeout 2 || true
    fi
    if [[ ${#built_images[@]} -gt 0 ]]; then
        docker image rm "${built_images[@]}" >/dev/null || true
    fi
    rm -rf -- "$REHEARSAL_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -z ${REHEARSAL_SERVER_IMAGE:-} ]]; then
    REHEARSAL_SERVER_IMAGE="$COMPOSE_PROJECT_NAME:server"
    docker build --tag "$REHEARSAL_SERVER_IMAGE" "$repo/infra/server-image"
    built_images+=("$REHEARSAL_SERVER_IMAGE")
fi
if [[ -z ${REHEARSAL_CONTROLLER_IMAGE:-} ]]; then
    REHEARSAL_CONTROLLER_IMAGE="$COMPOSE_PROJECT_NAME:controller"
    docker build --tag "$REHEARSAL_CONTROLLER_IMAGE" "$repo/tools/ansible"
    built_images+=("$REHEARSAL_CONTROLLER_IMAGE")
fi
export REHEARSAL_CONTROLLER_IMAGE REHEARSAL_SERVER_IMAGE

mkdir -p "$REHEARSAL_DIR"/{group_vars,public/accounts,public/v0.1.0} "$REHEARSAL_DIR/public/v$candidate"
cp "$1" "$REHEARSAL_DIR/public/v0.1.0/"
cp "$2" "$REHEARSAL_DIR/public/v$candidate/"
printf '%s\n' '{"id":1}' > "$REHEARSAL_DIR/public/accounts/1"
cp "$repo/infra/ansible/site.yml" "$REHEARSAL_DIR/"
cp -R "$repo/infra/ansible/roles" "$REHEARSAL_DIR/"
ssh-keygen -q -t ed25519 -N '' -C release-rehearsal -f "$REHEARSAL_DIR/key"
cat > "$REHEARSAL_DIR/inventory" <<'EOF'
[app]
server-1
server-2
[app:vars]
ansible_user=deploy
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/drill_known_hosts'
EOF
cat > "$REHEARSAL_DIR/group_vars/app.yml" <<EOF
deploy_public_keys:
  - "{{ lookup('ansible.builtin.file', '/drill/key.pub') }}"
orders_database_url: postgresql+psycopg://orders:$REHEARSAL_DB_PASSWORD@db:5432/orders
orders_accounts_url: http://controller:8080
orders_release_base_url: http://controller:8080
EOF

started=true
docker compose up -d --wait --wait-timeout 90
if [[ -n ${REHEARSAL_WHEELHOUSE:-} ]]; then
    mkdir "$REHEARSAL_DIR/public/dependencies"
    cp "$REHEARSAL_WHEELHOUSE"/*.whl "$REHEARSAL_DIR/public/dependencies/"
    cat > "$REHEARSAL_DIR/pip.conf" <<'EOF'
[global]
no-index = true
find-links = http://controller:8080/dependencies/
trusted-host = controller
EOF
    for node in server-1 server-2; do
        docker compose cp "$REHEARSAL_DIR/pip.conf" "$node:/etc/pip.conf"
    done
fi
python3 -u "$repo/tests/release/scenarios.py" "$candidate"
