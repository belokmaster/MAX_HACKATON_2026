FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*

ENV REQUESTS_CA_BUNDLE=/app/certs/Russian_Trusted_Root_CA.cer
ENV SSL_CERT_FILE=/app/certs/Russian_Trusted_Root_CA.cer
ENV PYTHONPATH=/app:/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data

COPY src/ ./src/

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
