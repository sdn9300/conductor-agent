# ==============================================================================
# Multi-Stage Production Dockerfile for Conductor Agent (#6)
# ==============================================================================

# ── Stage 1: Build & Dependency Wheel Cache ──────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ── Stage 2: Production Slim Runner ──────────────────────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH \
    PROMETHEUS_PORT=8001 \
    STORAGE_TYPE=sqlite \
    SQLITE_DB_PATH=/app/data/conductor_memory.db \
    PDF_OUTPUT_DIR=/app/data/pdf_resumes

# Copy installed python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Create non-root system user and app directories
RUN groupadd -g 1001 conductor && \
    useradd -u 1001 -g conductor -m -s /bin/bash conductor && \
    mkdir -p /app/data /app/data/pdf_resumes && \
    chown -R conductor:conductor /app

# Copy application source code
COPY --chown=conductor:conductor . /app/

# Switch to non-root user
USER conductor

# Expose Prometheus metrics port
EXPOSE 8001

# Healthcheck validating python execution
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import conductor.metrics, conductor.state; print('OK')" || exit 1

# Default entrypoint runs the Conductor CLI
ENTRYPOINT ["python", "-m", "conductor.cli"]
CMD ["daemon", "--interval-seconds", "3600"]
