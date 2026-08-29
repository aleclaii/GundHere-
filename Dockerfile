FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install \
    --no-cache-dir \
    --requirement requirements.txt

# Confirm that this Python build supports SQLite FTS5.
RUN python -c "import sqlite3; \
c = sqlite3.connect(':memory:'); \
c.execute('CREATE VIRTUAL TABLE test_fts USING fts5(content)')"

COPY . .

CMD ["python", "search.py", "gundam"]