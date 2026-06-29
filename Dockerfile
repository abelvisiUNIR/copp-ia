# Imagen única para todos los servicios Python de TeleFlow.
# El servicio concreto se selecciona con `command:` en docker-compose / Helm.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY teleflow ./teleflow
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

EXPOSE 8000 8001 8002 8003 8004

CMD ["uvicorn", "teleflow.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
