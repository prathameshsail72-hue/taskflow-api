FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN adduser --disabled-password --gecos "" taskflow && \
    mkdir -p /app/data && \
    chown -R taskflow:taskflow /app

USER taskflow

ENV DATABASE_URL=sqlite:////app/data/taskflow.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
