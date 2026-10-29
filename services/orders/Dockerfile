# Сборка образа сервиса заказов.

# ---------- этап 1: устанавливаем зависимости ----------
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
# Код копируется позже, поэтому его изменения не сбрасывают кеш зависимостей.
RUN python -c "import tomllib; print(*tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies'], sep='\n')" > requirements.txt \
    && python -m pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- этап 2: собираем итоговый образ ----------
FROM python:3.12-slim

# SQLite по умолчанию создаёт файл в рабочем каталоге.
RUN useradd --create-home --uid 1000 app \
    && install -d -o app -g app /app

COPY --from=builder /install /usr/local

WORKDIR /app
COPY orders ./orders
COPY alembic.ini ./
COPY migrations ./migrations

USER app
EXPOSE 8000
CMD ["uvicorn", "orders.main:app", "--host", "0.0.0.0", "--port", "8000"]
