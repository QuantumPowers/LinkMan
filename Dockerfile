# Dockerfile for LinkMan VPN

# Base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY setup.py .

# Install the package
RUN pip install -e .

# Create necessary directories
RUN mkdir -p /app/config /app/logs /app/metrics

# Expose ports
EXPOSE 8388 8443

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Command to run the server
CMD ["linkman-server", "start", "--config", "/app/config/server_config.json"]
