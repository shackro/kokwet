import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(tags=["Community members"])
Cohort = Literal["Campus Comrade", "Young Professional", "Creative Leader", "Established Elder"]


class ProfileCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(pattern=r"^(?:\+254|254|0)7\d{8}$")
    cohort: Cohort
    interest: str = Field(default="General ecosystem", max_length=120)


class JourneyProfileCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=80)
    phone_number: str = Field(pattern=r"^(?:\+254|254|0)7\d{8}$")
    audience_cohort: Cohort
    active_service_seeking: str = Field(default="General ecosystem", max_length=120)


def _database_path() -> Path:
    configured_path = os.getenv("KOKWET_DB_PATH")
    return Path(configured_path) if configured_path else Path(__file__).resolve().parents[1] / "data" / "kokwet.sqlite3"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_member_store() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS community_profiles (
                profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                cohort TEXT NOT NULL,
                interest TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )


def _profile_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["profile_id"],
        "full_name": row["full_name"],
        "phone": row["phone"],
        "cohort": row["cohort"],
        "interest": row["interest"],
        "verified": bool(row["verified"]),
        "created_at": row["created_at"],
    }


def _create_profile(payload: ProfileCreate) -> dict[str, object]:
    initialize_member_store()
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO community_profiles
                    (full_name, phone, cohort, interest, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.full_name.strip(),
                    payload.phone,
                    payload.cohort,
                    payload.interest.strip(),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            row = connection.execute(
                "SELECT * FROM community_profiles WHERE profile_id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="A profile already exists for this phone number") from error
    if row is None:
        raise RuntimeError("The newly registered profile could not be read back")
    return {"status": "success", "profile": _profile_payload(row)}


@router.post("/api/profiles", status_code=201)
def register_profile(payload: ProfileCreate) -> dict[str, object]:
    return _create_profile(payload)


@router.post("/api/v1/users/register", status_code=201)
def register_journey_profile(payload: JourneyProfileCreate) -> dict[str, object]:
    return _create_profile(
        ProfileCreate(
            full_name=payload.full_name,
            phone=payload.phone_number,
            cohort=payload.audience_cohort,
            interest=payload.active_service_seeking,
        )
    )
