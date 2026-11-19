"""Exercise releases over SSH and both published HTTP ports. Run via rehearse.sh."""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import nullcontext
from datetime import UTC, datetime
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

NODES = ("server-1", "server-2")
OLD = "0.1.0"
HTTP = build_opener(ProxyHandler({}))


def compose(*args, check=True):
    proc = subprocess.run(
        ["docker", "compose", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if check and proc.returncode:
        raise RuntimeError(f"docker compose {' '.join(args)}\n{proc.stdout}")
    return proc


def run_on(node, *args, check=True):
    return compose("exec", "-T", node, *args, check=check).stdout.strip()


def sql(query):
    return run_on(
        "db", "psql", "-U", "orders", "-d", "orders", "-At", "-v", "ON_ERROR_STOP=1", "-c", query
    )


def status(node, expected):
    line = run_on(node, "supervisorctl", "status", "orders", check=False)
    assert re.search(rf"^orders\s+{expected}\b", line), f"{node}: {line}"
    return line


def api(url, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url + path, data=data, headers={"Content-Type": "application/json"})
    with HTTP.open(request, timeout=3) as response:
        assert response.status == (201 if data else 200)
        return json.load(response)


def outage(url):
    try:
        api(url, "/health")
    except (URLError, ConnectionError, RemoteDisconnected, TimeoutError) as error:
        return str(error)
    raise AssertionError(f"{url}/health still responds successfully")


def check_health(url, version):
    health = api(url, "/health")
    expected = {"status": "ok", "service": "orders", "version": version}
    assert all(health.get(key) == value for key, value in expected.items()), health


def snapshot(node, url, version):
    check_health(url, version)
    target = run_on(node, "readlink", "-f", "/opt/orders/current")
    assert target == f"/opt/orders/releases/{version}", target
    line = status(node, "RUNNING")
    pid = re.search(r"\bpid (\d+),", line)
    assert pid and int(pid[1]) > 0, line
    return target, pid[1]


def deploy(version, digest=None, *, limit=None, expected_error=None, idempotent=False):
    command = ["ansible-playbook", "-i", "inventory", "site.yml", "-e", f"version=v{version}"]
    if digest:
        command.extend(
            ["-e", "release_repository=owner/repo", "-e", f"release_checksum=sha256:{digest}"]
        )
    if limit:
        command.extend(["--limit", limit])
    print("$", " ".join(command), flush=True)
    result = compose("exec", "-T", "controller", *command, check=False)
    recaps = re.findall(r"^server-[12]\s+: ok=.*$", result.stdout, re.MULTILINE)
    print("\n".join(recaps), flush=True)
    if expected_error:
        evidence = next(
            (
                line.strip()
                for line in result.stdout.splitlines()
                if re.search(expected_error, line, re.IGNORECASE)
            ),
            None,
        )
        assert result.returncode != 0 and evidence, result.stdout
        return evidence
    if result.returncode:
        raise RuntimeError(result.stdout)
    assert len(recaps) == (1 if limit else 2), result.stdout
    if idempotent:
        assert all(re.search(r"\bchanged=0\b", line) for line in recaps), recaps
    return "\n".join(recaps)


def rehearsal(directory, candidate, report):
    def note(title, detail):
        message = f"\n### {title}\n\n{detail}"
        print(message, flush=True)
        if report:
            print(message, file=report, flush=True)

    def since(start):
        return f"{time.monotonic() - start:.2f} s"

    urls = {n: "http://" + compose("port", n, "8000").stdout.strip() for n in NODES}
    sums = {}
    for version in (OLD, candidate):
        wheel = directory / "public" / f"v{version}" / f"orders-{version}-py3-none-any.whl"
        sums[version] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    note(
        "Стенд",
        f"{datetime.now(UTC).isoformat(timespec='seconds')}. Два сервера SSH с "
        "Supervisor и общим PostgreSQL. Внутренний HTTP-сервер раздаёт wheel и возвращает "
        "HTTP 200 на /accounts/1.\n\n" + "\n".join(f"- v{v} SHA256 `{s}`" for v, s in sums.items()),
    )

    first, second = NODES
    started = time.monotonic()
    deploy(OLD, sums[OLD])
    initial = {n: snapshot(n, urls[n], OLD) for n in NODES}
    old_revision = sql("SELECT version_num FROM alembic_version")
    nullable = (
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='orders' AND column_name='customer_note'"
    )
    assert old_revision == "483fb1e80029" and sql(nullable) == "", old_revision
    payload = {"account_id": 1, "item": "before-upgrade", "quantity": 1}
    baseline = api(urls[first], "/orders", payload)
    saved_path = f"/orders/{baseline['id']}"
    assert "customer_note" not in baseline and api(urls[second], saved_path) == baseline
    note(
        "Чистая установка",
        f"За {since(started)} оба /health вернули {OLD}, процессы "
        f"RUNNING, ревизия PostgreSQL `{old_revision}`. Заказ {baseline['id']} создан HTTP POST "
        "на первом сервере и прочитан на втором.",
    )

    recap = deploy(OLD, sums[OLD], idempotent=True)
    assert {n: snapshot(n, urls[n], OLD) for n in NODES} == initial
    note("Повторная установка", f"```text\n{recap}\n```\n\nОба PID и обе ссылки current сохранены.")

    started = time.monotonic()
    wrong = ("1" if sums[candidate][0] == "0" else "0") + sums[candidate][1:]
    evidence = deploy(candidate, wrong, expected_error=r"checksum.*did not match")
    detection = since(started)
    assert {n: snapshot(n, urls[n], OLD) for n in NODES} == initial
    assert sql("SELECT version_num FROM alembic_version") == old_revision
    note(
        "Неверная SHA256 нового wheel",
        f"От запуска до сообщения об ошибке {detection}. "
        f"\n\n```text\n{evidence}\n```\n\nОба /health вернули {OLD}, процессы RUNNING, "
        f"current и PID не изменились ({initial[first][1]}, {initial[second][1]}). "
        "Установка остановилась до миграции и переключения.",
    )

    started = time.monotonic()
    deploy(candidate, sums[candidate], limit=first)
    snapshot(first, urls[first], candidate)
    assert snapshot(second, urls[second], OLD) == initial[second]
    head = run_on(first, "/opt/orders/current/venv/bin/orders-migrate", "heads")
    revision = sql("SELECT version_num FROM alembic_version")
    assert f"{revision} (head)" in head and revision != old_revision and sql(nullable) == "YES"
    assert api(urls[first], saved_path)["customer_note"] is None
    new_order = api(
        urls[first], "/orders", dict(payload, item="after-upgrade", customer_note="keep")
    )
    new_path = f"/orders/{new_order['id']}"
    assert new_order["customer_note"] == "keep" and "customer_note" not in api(
        urls[second], new_path
    )
    mixed_order = api(urls[second], "/orders", dict(payload, item="mixed-old-writer"))
    assert api(urls[first], f"/orders/{mixed_order['id']}")["customer_note"] is None
    deploy(candidate, sums[candidate])
    for node in NODES:
        snapshot(node, urls[node], candidate)
        assert api(urls[node], new_path) == new_order
    note(
        "Обновление с верной SHA256",
        f"За {since(started)} проверены смешанная пара версий "
        f"и оба /health с {candidate}. Ревизия `{revision}`, поле customer_note допускает NULL. "
        f"Старая версия прочитала заказ {new_order['id']} и создала заказ {mixed_order['id']} "
        "после миграции. Новая версия видит все записи.",
    )

    for version in (OLD, candidate):
        (directory / "public" / f"v{version}").rename(directory / f"offline-v{version}")
        wheel_url = f"http://controller:8080/v{version}/orders-{version}-py3-none-any.whl"
        assert (
            run_on(first, "curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", wheel_url)
            == "404"
        )
    started = time.monotonic()
    deploy(OLD)
    for url in urls.values():
        check_health(url, OLD)
    elapsed = time.monotonic() - started
    for node in NODES:
        snapshot(node, urls[node], OLD)
        assert api(urls[node], saved_path) == baseline
        assert api(urls[node], new_path)["item"] == "after-upgrade"
    assert sql("SELECT version_num FROM alembic_version") == revision
    assert sql(f"SELECT customer_note FROM orders WHERE id = {int(new_order['id'])}") == "keep"
    note(
        "Откат из кеша",
        f"Оба URL wheel вернули HTTP 404. От запуска playbook до проверки "
        f"/health на обоих серверах **{elapsed:.2f} s**. Supervisor подтвердил RUNNING. "
        f"Оба сервера вернулись к {OLD}. Сохранились ревизия `{revision}` и customer_note.",
    )
    started = time.monotonic()
    run_on(first, "supervisorctl", "stop", "orders")
    symptom = outage(urls[first])
    stopped = status(first, "STOPPED")
    log = run_on(first, "supervisorctl", "tail", "orders", "stderr").splitlines()[-1]
    detection = since(started)
    other = snapshot(second, urls[second], OLD)
    started = time.monotonic()
    deploy(OLD)
    snapshot(first, urls[first], OLD)
    assert snapshot(second, urls[second], OLD) == other
    note(
        "Остановленный процесс",
        f"Обнаружение за {detection}. /health первого сервера: "
        f"`{symptom}`.\n\n```text\n{stopped}\n{log}\n```\n\nВосстановление тем же "
        f"playbook за {since(started)}. Оба /health вернули {OLD}, оба процесса RUNNING.",
    )

    started = time.monotonic()
    run_on(
        second,
        "sed",
        "-i",
        "/^command=/s/$/ --release-drill-invalid/",
        "/etc/supervisor/conf.d/orders.conf",
    )
    run_on(second, "supervisorctl", "reread")
    run_on(second, "supervisorctl", "update", "orders", check=False)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = run_on(second, "supervisorctl", "status", "orders", check=False)
        log = run_on(second, "supervisorctl", "tail", "orders", "stderr")
        errors = [line for line in log.splitlines() if "--release-drill-invalid" in line]
        if re.search(r"\b(BACKOFF|FATAL)\b", state) and errors:
            break
        time.sleep(0.5)
    else:
        raise AssertionError(f"Expected a supervised launch error\n{state}\n{log}")
    symptom = outage(urls[second])
    detection = since(started)
    other = snapshot(first, urls[first], OLD)
    started = time.monotonic()
    deploy(OLD)
    assert snapshot(first, urls[first], OLD) == other
    snapshot(second, urls[second], OLD)
    assert api(urls[second], saved_path) == baseline
    note(
        "Ошибка параметра запуска",
        f"Обнаружение за {detection}. /health второго сервера: "
        f"`{symptom}`.\n\n```text\n{state}\n{errors[-1]}\n```\n\nШаблон восстановлен тем же "
        f"playbook за {since(started)}. На обоих {OLD}, заказ {baseline['id']} сохранён.",
    )

    # Only the temporary controller copy is editable. Its template starts a real
    # candidate on 8003 while the production readiness check still probes 8000.
    template = directory / "roles/app/templates/orders.conf.j2"
    original = template.read_text()
    assert original.count("--port 8000") == 1, original
    peer = snapshot(second, urls[second], OLD)
    try:
        template.write_text(original.replace("--port 8000", "--port 8003"))
        started = time.monotonic()
        evidence = deploy(candidate, expected_error=r"status code was -1.*connection refused")
        detection = since(started)
        assert run_on(first, "readlink", "-f", "/opt/orders/current") == (
            f"/opt/orders/releases/{candidate}"
        )
        status(first, "RUNNING")
        outage(urls[first])
        misplaced = json.loads(run_on(first, "curl", "-fsS", "http://127.0.0.1:8003/health"))
        assert misplaced["version"] == candidate and misplaced["status"] == "ok", misplaced
        assert snapshot(second, urls[second], OLD) == peer
    finally:
        template.write_text(original)
        started = time.monotonic()
        deploy(OLD)
        snapshot(first, urls[first], OLD)
        assert snapshot(second, urls[second], OLD) == peer
    note(
        "Сбой проверки после переключения первого сервера",
        f"Первый сервер запустил {candidate} на 8003. На 8000 соединение отклонено. "
        f"За {detection} Ansible остановил обновление.\n\n```text\n{evidence}\n```\n\n"
        f"Второй сервер сохранил версию {OLD}, current и PID {peer[1]}. После возврата "
        f"шаблона оба /health подтвердили {OLD} за {since(started)}.",
    )
    assert elapsed < 60, f"Rollback exceeded one minute: {elapsed:.2f}s"


if __name__ == "__main__":
    report_path = os.getenv("REHEARSAL_REPORT")
    with open(report_path, "w", encoding="utf-8") if report_path else nullcontext() as report_file:
        rehearsal(Path(os.environ["REHEARSAL_DIR"]), sys.argv[1], report_file)
