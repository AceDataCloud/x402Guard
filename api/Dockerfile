# x402guard backend — Dockerfile
#
# Two-stage to keep the runtime image small. We pin Python and explicitly
# install dependencies via pip (not poetry) at runtime to avoid pulling
# poetry into the production image.

FROM python:3.12-slim AS builder

WORKDIR /build
COPY api/pyproject.toml ./

# Materialise a frozen requirements file we can install in the runtime
# stage without poetry. Mirrors the [tool.poetry.dependencies] section.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/install \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.5" \
        "sqlalchemy[asyncio]>=2.0" \
        "asyncpg>=0.29" \
        "aiosqlite>=0.20" \
        "solana>=0.34" \
        "solders>=0.21" \
        "httpx>=0.27" \
        "loguru>=0.7" \
        "pynacl>=1.5" \
        "cryptography>=43"


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Copy installed deps from the builder stage.
COPY --from=builder /install /usr/local/lib/python3.12/site-packages

# Copy our source.
COPY api ./api

# Run as a non-root user.
RUN useradd -r -u 1000 -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
