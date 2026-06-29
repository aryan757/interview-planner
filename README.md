# Interview Question Generator

A single FastAPI endpoint that generates domain- and seniority-calibrated
interview questions (each with a 0–1 relevance score) using **one** LangChain +
OpenAI GPT-4o call per request. Optional resume / job description are extracted
to plain text locally and folded into the same prompt.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`OPENAI_API_KEY` is read from `.env` (already present).

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs for the interactive Swagger UI, or POST to
`/generate-questions`.

## Request (multipart/form-data)

| Field | Required | Allowed values |
|---|---|---|
| `domain` | yes | `AI Engineer`, `Machine Learning`, `Computer Vision`, `MLOps`, `LLM Systems`, `Behavioral` |
| `intensity` | yes | `intern`, `senior`, `staff` |
| `interview_id` | yes | `aria`, `james`, `priya`, `patel` |
| `round_type` | yes | `warm-up`, `standard-technical`, `final-round` |
| `job_description` | no | free text |
| `resume` | no | `.pdf` or `.docx` file |

### Example (curl)

```bash
curl -X POST http://127.0.0.1:8000/generate-questions \
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
  "interview_id": "aria",
  "questions": [
    {"question": "How does QLoRA enable fine-tuning large models on consumer GPUs?", "score": 0.91},
    {"question": "What is the kernel trick in SVM?", "score": 0.74}
  ]
}
```

`interview_id` is a pass-through field injected in code after the LLM call — the
model only ever returns `{"questions": [...]}`.

## Layout

```
app/
├── main.py             # FastAPI app + the single POST endpoint
├── config.py           # constant maps (difficulty, counts, KB paths, enums)
├── kb_loader.py        # loads the per-domain knowledge base slice
├── document_extract.py # resume PDF/DOCX -> plain text (no LLM)
├── prompt_builder.py   # system + human prompt, conditional blocks
├── chain.py            # ChatOpenAI(gpt-4o) + structured output
└── schemas.py          # Pydantic request/response/LLM models
knowledge-base/         # per-domain KB .txt files
```
