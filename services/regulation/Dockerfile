FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY shared /shared
# [dev] extras on purpose: these are LOCAL DEV images, and the documented way to run a
# service suite is inside the stack (`docker compose exec -T <svc> python -m pytest`).
# Without pytest in the image that command only works after someone pip-installs by hand,
# which is exactly the kind of step that makes a test suite "green on my machine".
RUN pip install --no-cache-dir -e "/shared[dev]"

WORKDIR /app
COPY services/regulation /app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
