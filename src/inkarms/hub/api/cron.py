"""
Hub cron job CRUD endpoints.

GET  /api/cron          List all cron jobs from hub.db
POST /api/cron          Create a new cron job (persists to hub.db + registers with scheduler)
GET  /api/cron/{id}     Get a single cron job
DELETE /api/cron/{id}   Delete a cron job (removes from hub.db + unregisters from scheduler)
PATCH /api/cron/{id}/enable   Enable or disable a job
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from inkarms.hub import db as hub_db

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CronJobCreate(BaseModel):
    id: str
    schedule: str
    type: str = "bash"
    command: str
    session_id: str = "default"
    notify: str | None = None
    enabled: bool = True
    allowed_tools: list[str] | None = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ("bash", "ai_query"):
            raise ValueError("type must be 'bash' or 'ai_query'")
        return v

    @field_validator("schedule")
    @classmethod
    def _validate_schedule(cls, v: str) -> str:
        # Import lazily to avoid hard dependency at module load time
        from inkarms.hub.scheduler import _parse_schedule
        try:
            _parse_schedule(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not v or len(v) > 128:
            raise ValueError("id must be 1-128 characters")
        return v


class CronJobEnableRequest(BaseModel):
    enabled: bool


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an aiosqlite.Row to a plain dict."""
    return {
        "id": row["id"],
        "schedule": row["schedule"],
        "type": row["type"],
        "command": row["command"],
        "session_id": row["session_id"],
        "notify": row["notify"],
        "enabled": bool(row["enabled"]),
        "last_run": row["last_run"],
        "last_result": row["last_result"],
        "run_count": row["run_count"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/cron")
async def list_cron_jobs() -> dict[str, Any]:
    rows = await hub_db.execute_fetchall("SELECT * FROM cron_jobs ORDER BY id")
    return {"jobs": [_row_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/api/cron/{job_id}")
async def get_cron_job(job_id: str) -> dict[str, Any]:
    row = await hub_db.execute_fetchone(
        "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Cron job {job_id!r} not found")
    return _row_to_dict(row)


@router.post("/api/cron", status_code=201)
async def create_cron_job(body: CronJobCreate) -> dict[str, Any]:
    # Check for duplicate id
    existing = await hub_db.execute_fetchone(
        "SELECT id FROM cron_jobs WHERE id = ?", (body.id,)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Cron job {body.id!r} already exists")

    await hub_db.execute(
        """
        INSERT INTO cron_jobs (id, schedule, type, command, session_id, notify, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body.id,
            body.schedule,
            body.type,
            body.command,
            body.session_id,
            body.notify,
            1 if body.enabled else 0,
        ),
    )

    # Register with scheduler if enabled
    if body.enabled:
        try:
            from inkarms.hub import scheduler
            scheduler.add_job(body.model_dump())
        except RuntimeError:
            # Scheduler not started (e.g. during tests) — job is persisted to DB only
            pass

    row = await hub_db.execute_fetchone(
        "SELECT * FROM cron_jobs WHERE id = ?", (body.id,)
    )
    return _row_to_dict(row)


@router.delete("/api/cron/{job_id}")
async def delete_cron_job(job_id: str) -> dict[str, Any]:
    row = await hub_db.execute_fetchone(
        "SELECT id FROM cron_jobs WHERE id = ?", (job_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Cron job {job_id!r} not found")

    # Remove from scheduler first (silent if not found)
    try:
        from inkarms.hub import scheduler
        scheduler.remove_job(job_id)
    except RuntimeError:
        pass

    await hub_db.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
    return {"status": "deleted", "id": job_id}


@router.patch("/api/cron/{job_id}/enable")
async def set_cron_job_enabled(job_id: str, body: CronJobEnableRequest) -> dict[str, Any]:
    row = await hub_db.execute_fetchone(
        "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Cron job {job_id!r} not found")

    await hub_db.execute(
        "UPDATE cron_jobs SET enabled = ? WHERE id = ?",
        (1 if body.enabled else 0, job_id),
    )

    try:
        from inkarms.hub import scheduler
        if body.enabled:
            updated = await hub_db.execute_fetchone(
                "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
            )
            scheduler.add_job(dict(updated))
        else:
            scheduler.remove_job(job_id)
    except RuntimeError:
        pass

    updated_row = await hub_db.execute_fetchone(
        "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
    )
    return _row_to_dict(updated_row)
