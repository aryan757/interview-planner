"""Read voice interview evaluations from MongoDB."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

_client: Optional[AsyncIOMotorClient] = None

VOICE_INTERVIEWS = "voice_interviews"
VOICE_AGENT_PLANNER = "voice_agent_planner"
VGI_CONVERSATION = "vgi_conversation"


def _get_db():
    global _client
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        return None
    if _client is None:
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=6000)
    return _client.get_default_database()


def map_topic_to_domain(topic: str) -> str:
    """Mirror vgiskill-be/internal/interview/planner_client.go MapTopicToDomain."""
    topic = (topic or "").strip()
    direct = {
        "LLM Systems": "LLM Systems",
        "Computer Vision": "Computer Vision",
        "MLOps": "MLOps",
        "Machine Learning": "Machine Learning",
        "AI Engineer": "AI Engineer",
        "Behavioral": "Behavioral",
        "Behavioural": "Behavioral",
        "Edge AI": "AI Engineer",
        "Neural Networks": "Machine Learning",
        "AI Infrastructure": "MLOps",
        "Multimodal AI": "LLM Systems",
        "AI Agents": "LLM Systems",
    }
    return direct.get(topic, "AI Engineer")


async def get_latest_completed_interview(user_id: int) -> Optional[Dict[str, Any]]:
    db = _get_db()
    if db is None:
        return None
    return await db[VOICE_INTERVIEWS].find_one(
        {"userId": user_id, "status": "COMPLETED"},
        sort=[("completedAt", -1)],
    )


async def get_latest_conversation(user_id: int) -> Optional[Dict[str, Any]]:
    """Return the most recent saved voice-interview transcript for a user.

    The agent stores ``user_id`` as a string, but tolerate an int too."""
    db = _get_db()
    if db is None:
        return None
    candidates: List[Any] = [str(user_id), user_id]
    return await db[VGI_CONVERSATION].find_one(
        {"user_id": {"$in": candidates}},
        sort=[("created_at", -1)],
    )


async def get_latest_planner_doc(user_id: int) -> Optional[Dict[str, Any]]:
    """Return the most recent planner document for a user (carries the session
    metadata: request.domain/intensity/round_type and interview_id)."""
    db = _get_db()
    if db is None:
        return None
    return await db[VOICE_AGENT_PLANNER].find_one(
        {"user_id": str(user_id)},
        sort=[("created_at", -1)],
    )


async def get_planner_questions(user_id: int, topic: str) -> List[Dict[str, Any]]:
    db = _get_db()
    if db is None:
        return []
    domain = map_topic_to_domain(topic)
    col = db[VOICE_AGENT_PLANNER]
    doc = await col.find_one(
        {"user_id": str(user_id), "request.domain": domain},
        sort=[("created_at", -1)],
    )
    if doc is None:
        doc = await col.find_one({"user_id": str(user_id)}, sort=[("created_at", -1)])
    if not doc:
        return []
    return list(doc.get("questions") or [])
