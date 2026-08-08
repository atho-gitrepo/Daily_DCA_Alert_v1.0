# ============================================================
# DCA Day Trading Bot - Dockerfile (Production Ready)
# Version: 1.0.0
# ============================================================

FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with verbose output
RUN pip install --no-cache-dir -r requirements.txt && \
    pip list | grep -E "pandas|numpy|requests"

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/data && \
    chmod 755 /app/logs /app/data

# Create non-root user
RUN groupadd -r dca && useradd -r -g dca dca && \
    chown -R dca:dca /app

# Switch to non-root user
USER dca

# Expose health check port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application with unbuffered output
CMD ["python", "-u", "main.py"]
