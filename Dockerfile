FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y curl && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

RUN uv run playwright install chromium --with-deps --only-shell

COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

ENV PORT="8080"

CMD ["/app/bin/boot_server_in_docker"]