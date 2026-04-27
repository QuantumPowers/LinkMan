# Dockerfile for LinkMan VPN

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/config /app/logs /app/metrics

EXPOSE 8388 8389 8390

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

CMD ["linkman-server", "-c", "/app/config/linkman.toml"]
