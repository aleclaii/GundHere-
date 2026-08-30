FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

WORKDIR /app

COPY requirements-serving.txt .
RUN python -m pip install \
    --no-cache-dir \
    --requirement requirements-serving.txt

COPY fuzzy.py search_index.py vector_search.py hybrid_search.py server.py build_search_index.py ./
COPY client ./client
COPY data/processed/gunpla_ground_truth.csv ./data/processed/gunpla_ground_truth.csv

RUN python -c "import sqlite3; c = sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE test_fts USING fts5(content)')" \
    && python build_search_index.py \
    && chmod 0444 data/index/gundhere.sqlite3 \
    && groupadd --gid 10001 gundhere \
    && useradd --uid 10001 --gid gundhere --no-create-home --shell /usr/sbin/nologin gundhere

USER 10001:10001

EXPOSE 8000

CMD ["python", "server.py", "--host", "0.0.0.0"]
