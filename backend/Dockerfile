FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src

RUN pip install --no-cache-dir /app/backend

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
