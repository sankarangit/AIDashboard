FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY backend backend
COPY frontend frontend
COPY config config
COPY migrations migrations
RUN pip install --no-cache-dir .

EXPOSE 8000 8501
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
