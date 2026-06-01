FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y wget curl && \
  curl -LsSf https://astral.sh/uv/install.sh | sh && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install all dependencies including dev dependencies
RUN uv sync --frozen

# Install Playwright browser
RUN uv run playwright install chromium --with-deps --only-shell

COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

# Install minio client
RUN wget https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc && \
  chmod +x /usr/local/bin/mc

ENTRYPOINT ["./bin/run_locally"]

CMD ["uv", "run", "granian", "--reload", "--host", "0.0.0.0", "--port", "8200", "--interface", "asgi", "main:app"]
