"""FastAPI app exposing the single /generate-questions endpoint."""

from typing import Optional

from dotenv import load_dotenv

# Load OPENAI_API_KEY from .env before anything constructs an OpenAI client.
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app.chain import generate_question_set  # noqa: E402
from app.db import save_generation  # noqa: E402
from app.config import (  # noqa: E402
    ALLOWED_DOMAINS,
    ALLOWED_INTENSITIES,
    ALLOWED_INTERVIEW_IDS,
    ALLOWED_ROUND_TYPES,
    DIFFICULTY_MAP,
    QUESTION_COUNT_MAP,
)
from app.document_extract import extract_resume_text  # noqa: E402
from app.kb_loader import load_kb_slice  # noqa: E402
from app.prompt_builder import build_prompts  # noqa: E402
from app.evaluation import load_evaluation  # noqa: E402
from app.schemas import GenerateQuestionsResponse, EvaluationResponse  # noqa: E402

app = FastAPI(title="Interview Question Generator")

# Allow the browser frontend (a different origin, e.g. http://localhost:4321) to
# call this API directly. Configure with CORS_ALLOW_ORIGINS (comma-separated);
# defaults to "*" for local development.
import os  # noqa: E402

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")
    if o.strip()
] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Required form fields and their allowed values, surfaced in error responses so
# the caller knows exactly what to send for any permutation of missing fields.
REQUIRED_FIELDS = {
    "user_id": ["<any non-empty string>"],
    "domain": sorted(ALLOWED_DOMAINS),
    "intensity": sorted(ALLOWED_INTENSITIES),
    "interview_id": sorted(ALLOWED_INTERVIEW_IDS),
    "round_type": sorted(ALLOWED_ROUND_TYPES),
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a clean, actionable error instead of FastAPI's raw loc/msg dump.

    The common failure mode is a multipart request that omits one or more
    required fields (e.g. in Postman the row's checkbox is left unticked, so the
    field is never sent). We list precisely which required fields are missing.
    """
    missing = []
    other_errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = loc[-1] if loc else None
        if err.get("type") == "missing" and field in REQUIRED_FIELDS:
            missing.append(field)
        else:
            other_errors.append({"field": field, "msg": err.get("msg")})

    body = {
        "error": "Invalid request",
        "allowed_values": REQUIRED_FIELDS,
    }
    if missing:
        body["missing_required_fields"] = missing
        body["hint"] = (
            "These required fields were not received. In Postman (Body > form-data), "
            "tick the checkbox next to each of these rows — an unticked row is not sent."
        )
    if other_errors:
        body["other_errors"] = other_errors

    return JSONResponse(status_code=422, content=body)


def _validate(field: str, value: str, allowed: set) -> None:
    if value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field}: {value!r}. Allowed values: {sorted(allowed)}",
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/evaluation/{user_id}", response_model=EvaluationResponse)
async def get_evaluation(user_id: int):
    """Return the latest completed voice interview evaluation for a user."""
    result = await load_evaluation(user_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No completed voice interview evaluation found for user_id={user_id}",
        )
    return result


@app.post("/generate-questions", response_model=GenerateQuestionsResponse)
async def generate_questions(
    user_id: str = Form(...),
    domain: str = Form(...),
    intensity: str = Form(...),
    interview_id: str = Form(...),
    round_type: str = Form(...),
    job_description: Optional[str] = Form(None),
    resume: Optional[UploadFile] = File(None),
):
    # 1. Validate enums against config maps.
    _validate("domain", domain, ALLOWED_DOMAINS)
    _validate("intensity", intensity, ALLOWED_INTENSITIES)
    _validate("interview_id", interview_id, ALLOWED_INTERVIEW_IDS)
    _validate("round_type", round_type, ALLOWED_ROUND_TYPES)

    # 2. Extract resume text locally (None if absent/unsupported/empty).
    resume_text = None
    if resume is not None:
        data = await resume.read()
        resume_text = extract_resume_text(data, resume.filename)

    # Normalize an empty job_description string to None so its block is omitted.
    jd = job_description.strip() if job_description and job_description.strip() else None

    # 3. Load KB slice for the domain.
    kb_slice = load_kb_slice(domain)

    # 4. Map intensity -> difficulty, round_type -> num_questions.
    difficulty = DIFFICULTY_MAP[intensity]
    num_questions = QUESTION_COUNT_MAP[round_type]

    # 5. Build prompts with conditional blocks.
    system_prompt, human_prompt = build_prompts(
        domain=domain,
        difficulty=difficulty,
        num_questions=num_questions,
        kb_slice=kb_slice,
        resume_text=resume_text,
        job_description=jd,
    )

    # 6. Single LLM call -> validated QuestionSet.
    try:
        result = generate_question_set(system_prompt, human_prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}")

    # 7 & 8. Inject pass-through user_id + interview_id and build response.
    response = GenerateQuestionsResponse(
        user_id=user_id,
        interview_id=interview_id,
        questions=result.questions,
    )

    # 9. Persist the result to MongoDB (best-effort; never fails the request).
    await save_generation(
        user_id=user_id,
        interview_id=interview_id,
        domain=domain,
        intensity=intensity,
        round_type=round_type,
        difficulty=difficulty,
        num_questions=num_questions,
        job_description=jd,
        resume_provided=resume_text is not None,
        questions=[q.model_dump() for q in result.questions],
    )

    return response
