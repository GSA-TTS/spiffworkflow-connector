# Base image to share ENV vars that activate VENV.
FROM python:3.11.6-slim-bookworm AS base

# ENV VIRTUAL_ENV=/app/venv
# RUN python3 -m venv $VIRTUAL_ENV
# ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright


######################## - DEPLOYMENT

# base plus packages needed for deployment. Could just install these in final, but then we can't cache as much.
# vim is just for debugging
FROM base AS deployment

# git-core because the app does "git commit", etc
# curl because the docker health check uses it
# procps because it is useful for debugging
# gunicorn3 for web server
# default-mysql-client for convenience accessing mysql docker container
# vim ftw
RUN apt-get update \
  && apt-get clean -y \
  && apt-get install -y -q git-core curl procps gunicorn3 default-mysql-client vim-tiny libkrb5support0 libexpat1 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

COPY ./bin ./bin/
COPY ./connector-pdf ./connector-pdf/

######################## - SETUP

# Setup image for installing Python dependencies.
FROM base AS setup

# poetry 1.4 seems to cause an issue where it errors with
#   This error originates from the build backend, and is likely not a
#   problem with poetry but with lazy-object-proxy (1.7.1) not supporting PEP 517 builds.
#   You can verify this by running 'pip wheel --use-pep517 "lazy-object-proxy (==1.7.1) ; python_version >= "3.6""'.
# Pinnning to 1.3.2 to attempt to avoid it.

# Install poetry in /opt/poetry
# RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -
# ENV PATH="${PATH}:/opt/poetry/bin"

COPY pyproject.toml poetry.lock ./
COPY ./connector-pdf ./connector-pdf/

RUN pip install poetry


# Add the current directory to the PYTHONPATH
# ENV PYTHONPATH="${PYTHONPATH}:/app"

RUN useradd _gunicorn --no-create-home --user-group

RUN apt-get update \
  && apt-get install -y -q gcc libssl-dev pkg-config git

# Install poetry dependencies
RUN poetry install
# Install playwright browsers
RUN poetry run playwright install chromium --with-deps --only-shell


# Install dependencies and start app
# WORKDIR /app
# COPY pyproject.toml poetry.lock ./
# RUN poetry self add poetry-plugin-export
# RUN poetry export -f requirements.txt --without-hashes --output requirements.txt
# RUN cat requirements.txt
# RUN pip install -r requirements.txt


# # Playwright (2 part install doesn't require root)
# ## Install playwright browser deps
# RUN poetry run playwright install-deps chromium
# ## Install Chromium 
# RUN poetry run playwright install chromium --only-shell


######################## - FINAL

# Final image without setup dependencies.
FROM deployment AS final

LABEL source="https://github.com/GSA-TTS/spiffworkflow-connector"
LABEL description="Spiffworkflow Connector for GSA-TTS SpiffWorkflow instances"

COPY --from=setup /app /app/

CMD ["./bin/run_server_for_cloud"]
