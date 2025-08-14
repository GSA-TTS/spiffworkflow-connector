FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium --with-deps --only-shell

# Install minio client
RUN apt-get update && apt-get install -y wget
RUN wget https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc && \
  chmod +x /usr/local/bin/mc

ENTRYPOINT ["./bin/run_locally"]

CMD [ "granian", "--reload", "--host", "0.0.0.0", "--port", "8200", "--interface", "asgi", "main:app" ]
