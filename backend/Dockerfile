FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY mandatory ./mandatory
COPY bonus ./bonus
RUN pip install --no-cache-dir . && useradd --create-home music && chown -R music:music /app
COPY alembic.ini ./
COPY alembic ./alembic
USER music
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
