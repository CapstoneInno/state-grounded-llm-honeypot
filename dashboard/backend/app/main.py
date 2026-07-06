from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .reader import get_session, get_sessions

app = FastAPI(title="State-Grounded Dashboard")


@app.get("/api/sessions")
def sessions():
    return get_sessions()


@app.get("/api/sessions/{session_id}")
def session(session_id: str):
    events = get_session(session_id)

    if not events:
        raise HTTPException(status_code=404, detail="Session not found")

    return events
