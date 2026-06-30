# Interview Question Generator

A single FastAPI endpoint that generates domain- and seniority-calibrated
interview questions (each with a 0–1 relevance score) using **one** LangChain +
OpenAI GPT-4o call per request. Optional resume / job description are extracted
to plain text locally and folded into the same prompt. Every successful
generation is persisted to MongoDB.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configuration is read from `.env` (already present):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI key for the GPT-4o call |
| `DATABASE_URL` | MongoDB connection string; results are saved to the `voice_agent_planner` collection of the database named in this URL. If unset, the app still runs without persistence. |

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs for the interactive Swagger UI, or POST to
`/generate-questions`.

## Request (multipart/form-data)

| Field | Required | Allowed values |
|---|---|---|
| `user_id` | yes | any non-empty string |
| `domain` | yes | `AI Engineer`, `Machine Learning`, `Computer Vision`, `MLOps`, `LLM Systems`, `Behavioral` |
| `intensity` | yes | `intern`, `senior`, `staff` |
| `interview_id` | yes | `aria`, `james`, `priya`, `patel` |
| `round_type` | yes | `warm-up`, `standard-technical`, `final-round` |
| `job_description` | no | free text |
| `resume` | no | `.pdf` or `.docx` file |

> In Postman (Body → form-data), make sure the checkbox next to each required
> row is ticked — an unticked row is not sent and will return a `422` listing the
> missing fields.

### Example (curl)

```bash
curl -X POST http://127.0.0.1:8000/generate-questions \
  -F "user_id=user_42" \
  -F "domain=LLM Systems" \
  -F "intensity=senior" \
  -F "interview_id=aria" \
  -F "round_type=standard-technical" \
  -F "job_description=Hiring an LLM engineer to own our RAG pipeline." \
  -F "resume=@/path/to/resume.pdf"
```

## Response

```json
{
  "user_id": "user_42",
  "interview_id": "aria",
  "questions": [
    {"question": "How does QLoRA enable fine-tuning large models on consumer GPUs?", "score": 0.91},
    {"question": "What is the kernel trick in SVM?", "score": 0.74}
  ]
}
```

`user_id` and `interview_id` are pass-through fields injected in code after the
LLM call — the model only ever returns `{"questions": [...]}`.

## Persistence

Each successful response is written to the `voice_agent_planner` collection in
MongoDB (`DATABASE_URL`). Saving is best-effort — a database error is logged but
never fails the request. Each document stores the output plus request context:

```json
{
  "user_id": "user_42",
  "interview_id": "aria",
  "request": {
    "domain": "LLM Systems",
    "intensity": "senior",
    "round_type": "standard-technical",
    "difficulty": "medium",
    "num_questions": 10,
    "job_description": "...",
    "resume_provided": true
  },
  "questions": [ {"question": "...", "score": 0.91} ],
  "created_at": "2026-06-30T12:00:00Z"
}
```

## Layout

```
app/
├── main.py             # FastAPI app + the single POST endpoint
├── config.py           # constant maps (difficulty, counts, KB paths, enums)
├── kb_loader.py        # loads the per-domain knowledge base slice
├── document_extract.py # resume PDF/DOCX -> plain text (no LLM)
├── prompt_builder.py   # system + human prompt, conditional blocks
├── chain.py            # ChatOpenAI(gpt-4o) + structured output
├── schemas.py          # Pydantic request/response/LLM models
└── db.py               # MongoDB persistence (voice_agent_planner collection)
knowledge-base/         # per-domain KB .txt files
```
