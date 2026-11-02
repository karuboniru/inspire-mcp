FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM docker.io/library/python:3.13-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-cache

FROM docker.io/library/python:3.13-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["inspire-mcp"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000", "--allow-public-http"]
