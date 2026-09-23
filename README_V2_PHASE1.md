# RepoPilot V2 - Phase 1/2 overlay

This overlay upgrades the current RepoPilot repository with:

- PostgreSQL persistence for RepairTask / RepairAttempt / TraceEvent
- SQLAlchemy 2.x models
- Alembic migration
- persistent `/tasks` API
- existing `/repair` kept for compatibility
- trace event persistence without rewriting the existing workflow
- optional Celery + Redis execution mode
- default `inline` mode so PostgreSQL can be verified before Redis/Celery

## Apply the overlay

Copy the contents of this archive into the root of your existing RepoPilot repository and allow replacement of:

- `pyproject.toml`
- `src/repo_pilot/api.py`
- `src/repo_pilot/trace.py`

All other files are new.

## First run: PostgreSQL only

PowerShell commands from the RepoPilot repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .

docker compose up -d postgres

$env:DATABASE_URL="postgresql+psycopg://repopilot:repopilot@127.0.0.1:5432/repopilot"
$env:REPOPILOT_TASK_MODE="inline"
$env:REPOPILOT_ALLOWED_ROOT=(Get-Location).Path

alembic upgrade head
python -m uvicorn repo_pilot.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`.

For the current example repo, call `POST /tasks` with something like:

```json
{
  "repo": "D:/your-path/repopilot/examples/buggy_calculator",
  "issue": "divide by zero should raise ValueError",
  "test_command": "python -m pytest -q",
  "provider": "fake",
  "model": "fake-model",
  "max_iterations": 2,
  "apply_patch": true,
  "command_timeout_sec": 120
}
```

Then inspect:

- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/attempts`
- `GET /tasks/{task_id}/trace`

## Verify the database directly

```powershell
docker exec -it repopilot-postgres psql -U repopilot -d repopilot
```

Inside psql:

```sql
\dt
SELECT id, status, current_stage, current_iteration, success
FROM repair_tasks
ORDER BY id DESC;

SELECT id, task_id, attempt_no, status, stage
FROM repair_attempts
ORDER BY id;

SELECT id, task_id, attempt_id, stage, event_type
FROM trace_events
ORDER BY id;
```

Use `\q` to exit.

## Switch to Celery later

After the inline mode works:

```powershell
docker compose up -d redis
$env:REPOPILOT_TASK_MODE="celery"
$env:REPOPILOT_REDIS_URL="redis://127.0.0.1:6379/0"

celery -A repo_pilot.worker.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

Keep the API running in another terminal. `POST /tasks` will then return after queueing and the Celery worker will execute the Agent.

On Windows, `--pool=solo` avoids common multiprocessing issues during development.
