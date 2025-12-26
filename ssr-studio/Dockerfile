# SSR Studio Backend Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv for fast package management
RUN pip install uv

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY configs/ ./configs/

# Install Python dependencies
RUN uv pip install --system -e ".[dev]"

# Create non-root user
RUN useradd -m -u 1000 ssr && \
    chown -R ssr:ssr /app

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV SSR_STUDIO_CONFIG=/app/configs/default.yaml

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run as non-root user
USER ssr

# Start the application
CMD ["uvicorn", "ssr_studio.api:app", "--host", "0.0.0.0", "--port", "8000"]
