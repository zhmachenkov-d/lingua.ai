FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
# Shared max turn length SoT (canonical file lives under apps/web).
COPY apps/web/src/app/chat/max-turn-text-length.json ./contracts/max-turn-text-length.json

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
