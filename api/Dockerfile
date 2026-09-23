FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей Python с использованием стандартных системных сертификатов
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Настройка переменных окружения для runtime
ENV SSL_CERT_FILE=/app/certs/Russian_Trusted_Root_CA.cer
ENV REQUESTS_CA_BUNDLE=/app/certs/Russian_Trusted_Root_CA.cer
ENV PYTHONPATH=/app:/app/src

RUN mkdir -p /app/data

COPY src/ ./src/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
