FROM python:3.12-slim AS base

WORKDIR /app

# Set the browsers path to a location outside of the /app directory
# so that bind-mounts of the app code don't overwrite it.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

RUN pip install --upgrade pip
RUN pip install poetry==1.8.1 pytest-xdist==3.5.0

COPY . /app/

# COPY pyproject.toml poetry.lock* /app/
# COPY connector-pdf/ /app/connector-pdf/
RUN poetry install --only main
RUN poetry run playwright install chromium --with-deps --only-shell

# install minio client
RUN apt-get update && apt-get install -y wget
RUN wget https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc && \
  chmod +x /usr/local/bin/mc

# Copy our custom entrypoint
# COPY bin/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /app/bin/docker-entrypoint.sh
RUN chmod +x /app/bin/run_server_locally

ENTRYPOINT ["/app/bin/docker-entrypoint.sh"]
CMD ["/app/bin/run_server_locally"]
