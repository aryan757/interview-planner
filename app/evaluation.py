"""Build the evaluation API response by scoring a saved voice-interview transcript.

The candidate's spoken interview is saved to the ``vgi_conversation`` collection
by the voice agent. This module fetches the latest transcript for a user, sends
the questions + answers to the LLM for scoring, and derives every field of the
frontend contract dynamically (band, colour, xp, certification, delivery, ...).

Session metadata (topic, interview_type, intensity, interviewer) is read from the
transcript document when present, falling back to the latest planner document.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.chain import score_conversation
from app.evaluation_store import (
    get_latest_conversation,
    get_latest_planner_doc,
)
from app.schemas import (
    ConversationScore,
    DimensionBreakdown,
    EvaluationQuestionReview,
    EvaluationResponse,
)

VOICE_WEIGHT_TECHNICAL = 40
VOICE_WEIGHT_DEPTH = 25
VOICE_WEIGHT_COMMUNICATION = 20
VOICE_WEIGHT_PROBLEM_SOLVING = 15
QUESTION_MAX_SCORE = 40

CERT_MIN_SCORE = 70
XP_VOICE_MIN = 20
XP_VOICE_MAX = 70

COLOR_STRONG = "#10B981"
COLOR_SOLID = "#6C5CE7"
COLOR_DEVELOPING = "#F59E0B"
COLOR_NEEDS = "#EF4444"

FILLER_WORDS = ["um", "uh", "erm", "hmm", "uhh", "umm", "basically", "actually", "literally"]
FILLER_PHRASES = ["you know", "i mean", "sort of", "kind of", "kinda", "like i said"]

SCORING_SYSTEM_PROMPT = (
    "You are an experienced but fair technical interviewer scoring a voice "
    "interview. You are given the questions asked and the candidate's spoken "
    "answers.\n\n"
    "Judge at an EASY-TO-MEDIUM level, focusing on INTENT and understanding "
    "rather than perfect wording:\n"
    "- If an answer shows the candidate genuinely understands the concept and is "
    "heading in the right direction, score it well even if it is not "
    "textbook-perfect or a bit rough (these are spoken, informal answers).\n"
    "- Give partial credit for partially correct or incomplete answers.\n"
    "- Score low for answers that are wrong, empty, 'I don't know', or off-topic.\n"
    "- Do not penalize small grammatical issues or filler words from speech.\n\n"
    "Score every dimension as a PERCENT from 0 to 100. Return ONE question review "
    "for EACH question, in the order asked."
)


# --- Score-derived helpers ------------------------------------------------------

def _score_band(score: int) -> str:
    if score >= 81:
        return "strong"
    if score >= 61:
        return "solid"
    if score >= 31:
        return "developing"
    return "needs_fundamentals"


def _band_label(score: int) -> str:
    if score >= 81:
        return "Strong Candidate"
    if score >= 61:
        return "Solid Candidate"
    if score >= 31:
        return "Developing Candidate"
    return "Building Foundations"


def _score_color(score: int) -> str:
    if score >= 81:
        return COLOR_STRONG
    if score >= 61:
        return COLOR_SOLID
    if score >= 31:
        return COLOR_DEVELOPING
    return COLOR_NEEDS


def _xp_earned(score: int) -> int:
    s = max(0, min(100, score))
    return round(XP_VOICE_MIN + (s / 100) * (XP_VOICE_MAX - XP_VOICE_MIN))


def _dimension_points(pct: Optional[int], weight: int) -> DimensionBreakdown:
    p = max(0, min(100, int(pct or 0)))
    return DimensionBreakdown(points=round((p / 100) * weight), max=weight, percent=p)


# --- Delivery helpers (derived from the transcript) -----------------------------

def _count_fillers(conversation: List[Dict[str, Any]]) -> int:
    text = " ".join((turn.get("answer") or "").lower() for turn in conversation)
    if not text.strip():
        return 0
    count = sum(text.count(phrase) for phrase in FILLER_PHRASES)
    for word in re.findall(r"[a-z']+", text):
        if word in FILLER_WORDS:
            count += 1
    return count


def _compute_pace_wpm(conversation: List[Dict[str, Any]]) -> int:
    total_words = 0
    total_seconds = 0.0
    for turn in conversation:
        seconds = turn.get("answer_seconds")
        if not seconds or seconds <= 0:
            continue
        words = turn.get("answer_words")
        if words is None:
            words = len((turn.get("answer") or "").split())
        total_words += words
        total_seconds += seconds
    if total_seconds <= 0:
        return 0
    return round(total_words / (total_seconds / 60))


def _pace_label(pace_wpm: int) -> str:
    if pace_wpm <= 0:
        return "N/A"
    return "Optimal" if 120 <= pace_wpm <= 160 else "Adjust"


def _filler_label(filler_count: int) -> str:
    if filler_count <= 3:
        return "Excellent"
    if filler_count <= 8:
        return "Moderate"
    return "High"


def _confidence(pace_wpm: int, filler_count: int) -> str:
    pace_score = 1.0 if 120 <= pace_wpm <= 160 else 0.7
    filler_ratio = min(1.0, filler_count / 15.0)
    score = 0.6 * pace_score + 0.4 * (1 - filler_ratio)
    if score >= 0.82:
        return "Strong"
    if score >= 0.68:
        return "Good"
    return "Needs work"


# --- Transcript / metadata helpers ---------------------------------------------

def _format_transcript(conversation: List[Dict[str, Any]]) -> str:
    lines = []
    for i, turn in enumerate(conversation, 1):
        label = "Follow-up" if turn.get("type") == "followup" else "Question"
        lines.append(f"{label} {i}: {turn.get('question', '')}")
        lines.append(f"Answer {i}: {turn.get('answer') or '(no answer)'}\n")
    return "\n".join(lines)


def _resolve_meta(conversation_doc: Dict[str, Any], planner_doc: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Prefer metadata saved on the transcript; fall back to the planner doc."""
    request = (planner_doc or {}).get("request") or {}
    interview_id = conversation_doc.get("interview_id") or (planner_doc or {}).get("interview_id") or ""
    interviewer = conversation_doc.get("interviewer") or (interview_id.capitalize() if interview_id else "")
    return {
        "interview_id": interview_id,
        "topic": conversation_doc.get("topic") or request.get("domain") or "",
        "interview_type": conversation_doc.get("interview_type") or request.get("round_type") or "",
        "intensity": conversation_doc.get("intensity") or request.get("intensity") or "",
        "interviewer": interviewer,
    }


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(dt)


def _build_question_reviews(
    conversation: List[Dict[str, Any]],
    score: ConversationScore,
) -> List[EvaluationQuestionReview]:
    reviews: List[EvaluationQuestionReview] = []
    llm_reviews = score.question_reviews or []
    for i, turn in enumerate(conversation):
        rev = llm_reviews[i] if i < len(llm_reviews) else None
        percent = int(rev.percent) if rev else 0
        reviews.append(
            EvaluationQuestionReview(
                question=str(turn.get("question") or ""),
                score=round((percent / 100) * QUESTION_MAX_SCORE),
                max_score=QUESTION_MAX_SCORE,
                good=rev.good if rev else "",
                improve=rev.improve if rev else "",
            )
        )
    return reviews


async def load_evaluation(user_id: int) -> Optional[EvaluationResponse]:
    """Fetch the latest transcript for ``user_id``, score it, and build the report.

    Returns None (-> 404) when the user has no saved voice-interview transcript."""
    conversation_doc = await get_latest_conversation(user_id)
    if not conversation_doc:
        return None

    conversation: List[Dict[str, Any]] = conversation_doc.get("conversation") or []
    if not conversation:
        return None

    score = score_conversation(SCORING_SYSTEM_PROMPT, _format_transcript(conversation))

    dims = score.dimensions
    dimensions = {
        "technical": _dimension_points(dims.technical, VOICE_WEIGHT_TECHNICAL),
        "depth": _dimension_points(dims.depth, VOICE_WEIGHT_DEPTH),
        "communication": _dimension_points(dims.communication, VOICE_WEIGHT_COMMUNICATION),
        "problem_solving": _dimension_points(dims.problem_solving, VOICE_WEIGHT_PROBLEM_SOLVING),
    }
    final_score = sum(d.points for d in dimensions.values())

    planner_doc = await get_latest_planner_doc(user_id)
    meta = _resolve_meta(conversation_doc, planner_doc)

    pace_wpm = _compute_pace_wpm(conversation)
    filler_count = _count_fillers(conversation)
    created_iso = _iso(conversation_doc.get("created_at"))

    return EvaluationResponse(
        user_id=user_id,
        interview_id=meta["interview_id"] or str(conversation_doc.get("_id")),
        topic=meta["topic"],
        interview_type=meta["interview_type"],
        intensity=meta["intensity"],
        interviewer=meta["interviewer"],
        status="completed",
        final_score=final_score,
        score_band=_score_band(final_score),
        score_color=_score_color(final_score),
        band_label=_band_label(final_score),
        certified=final_score >= CERT_MIN_SCORE,
        xp_earned=_xp_earned(final_score),
        dimensions=dimensions,
        delivery={
            "pace_wpm": pace_wpm,
            "pace_label": _pace_label(pace_wpm),
            "filler_count": filler_count,
            "filler_label": _filler_label(filler_count),
            "confidence": _confidence(pace_wpm, filler_count),
        },
        question_reviews=_build_question_reviews(conversation, score),
        completed_at=created_iso,
        created_at=created_iso,
    )
