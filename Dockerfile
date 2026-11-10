FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code is also live-mounted by docker-compose; this copy is the fallback for a plain build
COPY cfb ./cfb

# Run as a non-root user
RUN useradd --create-home --uid 1000 cfb
USER cfb
