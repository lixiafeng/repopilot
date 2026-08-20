FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

COPY examples ./examples

RUN mkdir -p /app/runs

ENV REPOPILOT_ALLOWED_ROOT=/workspace
ENV REPOPILOT_TRACE_DIR=/app/runs

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "repo_pilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
