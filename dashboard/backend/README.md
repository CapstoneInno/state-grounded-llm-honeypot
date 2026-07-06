# Dashboard Backend

Run:

```bash
python -m uvicorn dashboard.backend.app.main:app --reload
```

Endpoints:

```
GET /api/sessions
GET /api/sessions/{id}
```

Environment:

```bash
export MIDDLEWARE_EVENTS_LOG=var/sglh-events.jsonl
```
