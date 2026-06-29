"""MongoDB persistence for generated question sets.

Each successful call to /generate-questions is saved to the `voice_agent_planner`
collection. Saving is a side effect — a DB failure must never break question
generation, so callers should treat save errors as non-fatal.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient

COLLECTION_NAME = "voice_agent_planner"

_client: Optional[AsyncIOMotorClient] = None


def _get_collection():
    """Lazily create a single shared async client and return the collection.

    Returns None if DATABASE_URL is not configured, so the app still runs
    (just without persistence).
    """
    global _client
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        return None

    if _client is None:
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=6000)

    # The db name is taken from DATABASE_URL (vgi_skill_lab here).
    db = _client.get_default_database()
    return db[COLLECTION_NAME]


async def save_generation(
    *,
    interview_id: str,
    domain: str,
    intensity: str,
    round_type: str,
    difficulty: str,
    num_questions: int,
    job_description: Optional[str],
    resume_provided: bool,
    questions: list,
) -> Optional[str]:
    """Persist one generation result. Returns the inserted _id (str) or None.

    Never raises — on any failure it returns None so the request still succeeds.
    """
    collection = _get_collection()
    if collection is None:
        return None

    document: Dict[str, Any] = {
        "interview_id": interview_id,
        "request": {
            "domain": domain,
            "intensity": intensity,
            "round_type": round_type,
            "difficulty": difficulty,
            "num_questions": num_questions,
            "job_description": job_description,
            "resume_provided": resume_provided,
        },
        "questions": questions,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = await collection.insert_one(document)
        return str(result.inserted_id)
    except Exception:
        # Persistence is best-effort; don't fail the API call over it.
        return None
