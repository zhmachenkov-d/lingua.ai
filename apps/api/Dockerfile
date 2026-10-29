FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Path dep is resolved by uv locally; Docker installs the shared package explicitly.
COPY packages/lingua_ids /packages/lingua_ids
COPY packages/lingua_corpus /packages/lingua_corpus
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
# Shared max turn length SoT (canonical file lives under apps/web).
COPY apps/web/src/app/chat/max-turn-text-length.json ./contracts/max-turn-text-length.json

RUN pip install --no-cache-dir /packages/lingua_ids \
 && pip install --no-cache-dir /packages/lingua_corpus \
 && python -c "from pathlib import Path; p=Path('pyproject.toml'); t=p.read_text(); p.write_text(t.replace('  \"lingua-ids\",\n', '').replace('  \"lingua-corpus\",\n', ''))" \
 && pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
