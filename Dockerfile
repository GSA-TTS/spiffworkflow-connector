FROM python:3.12-slim

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium --with-deps --only-shell

COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

ENV PORT="8080"

CMD ["/app/bin/boot_server_in_docker"]

