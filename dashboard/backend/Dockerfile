FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY middleware/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY middleware/src ./src

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV SGLH_LOG_LEVEL=INFO
ENV SGLH_EVENTS_LOG=/var/log/sglh/events.json
ENV SGLH_BRIDGE_PORT=8000

EXPOSE 8000

VOLUME ["/var/log/sglh"]

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "state_grounded.cowrie_bridge"]
