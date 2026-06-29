# Interview Question Generator — Build Spec

## 1. Overview

A single API endpoint that takes interview-setup parameters (via Postman/HTTP POST), optionally a resume and/or job description, and returns a list of AI-generated interview questions, each with a relevance score (0–1), using LangChain + OpenAI GPT-4o.

**Core principle: ONE LLM call per request.** No multi-step chains, no separate extraction call. Resume/JD text (if provided) is extracted to plain text locally (no LLM) and passed directly into the same prompt that generates questions. This minimizes latency.

---

## 2. Request Schema (Postman / HTTP POST, multipart/form-data)

| Field | Type | Required | Allowed values |
|---|---|---|---|
| `domain` | string | Yes | `AI Engineer`, `Machine Learning`, `Computer Vision`, `MLOps`, `LLM Systems`, `Behavioral` |
| `intensity` | string | Yes | `intern`, `senior`, `staff` |
| `interview_id` | string | Yes | `aria`, `james`, `priya`, `patel` |
| `round_type` | string | Yes | `warm-up`, `standard-technical`, `final-round` |
| `resume` | file (pdf/docx) | No | — |
| `job_description` | string (free text) | No | — |

### Field → logic mapping (fixed constants, defined in code, easy to tune later)

```python
DIFFICULTY_MAP = {
    "intern": "easy",
    "senior": "medium",
    "staff": "tough",
}

QUESTION_COUNT_MAP = {
    "warm-up": 6,              # range given was 5-7
    "standard-technical": 10,  # range given was 8-12
    "final-round": 15,         # fixed at 15
}

DOMAIN_TO_KB_FILE = {
    "AI Engineer": "kb/ai_engineer.txt",
    "Machine Learning": "kb/machine_learning.txt",
    "Computer Vision": "kb/computer_vision.txt",
    "MLOps": "kb/mlops.txt",
    "LLM Systems": "kb/llm_systems.txt",
    "Behavioral": "kb/behavioral.txt",
}
```

---

## 3. Response Schema (what your API returns to Postman)

```json
{
  "interview_id": "aria",
  "questions": [
    {"question": "How does QLoRA enable fine-tuning large models on consumer GPUs?", "score": 0.91},
    {"question": "What is the kernel trick in SVM?", "score": 0.74}
  ]
}
```

- `interview_id` is **injected by Python after the LLM call** — it is a pass-through field from the request, never generated or judged by the LLM. This avoids any risk of the model mistyping/dropping it.
- The LLM itself only ever returns `{"questions": [...]}` — `interview_id` is added afterward in code.
- `score` (0–1) = relevance of that specific question to the candidate's domain + intensity + (resume/JD fit, if provided). When resume/JD are absent, score reflects fit to domain + intensity + knowledge base alone.

---

## 4. Folder Structure

```
project/
├── kb/
│   ├── ai_engineer.txt
│   ├── machine_learning.txt
│   ├── computer_vision.txt
│   ├── mlops.txt
│   ├── llm_systems.txt
│   └── behavioral.txt
├── app/
│   ├── main.py              # FastAPI app, the single POST endpoint
│   ├── config.py            # the constant maps from section 2
│   ├── kb_loader.py          # loads the right kb/*.txt file based on domain
│   ├── document_extract.py   # resume/docx/pdf -> plain text (NO LLM call)
│   ├── prompt_builder.py     # builds system + human prompt, conditional on resume/JD presence
│   ├── chain.py              # LangChain: ChatOpenAI(gpt-4o) + prompt -> structured JSON output
│   └── schemas.py            # Pydantic models for request/response validation
├── requirements.txt
└── .env                      # OPENAI_API_KEY
```

> Knowledge base `.txt` files (the 6 per-domain files) are assumed already generated — drop them into `kb/` as-is. Each file is pipe-delimited dense text, one line per topic: `Topic||subtopics (semicolon-separated)||E:easy example||M:medium example||T:tough example`.

---

## 5. Document Extraction (`document_extract.py`)

Pure local extraction, no LLM involved — keep this fast and synchronous.

- PDF → use `pypdf` (`PdfReader`, concatenate `page.extract_text()` across pages).
- DOCX → use `python-docx` (`Document`, concatenate `paragraph.text` across paragraphs).
- If file is missing/not provided → return `None`, and the prompt builder must skip the resume section entirely (see section 6 — no placeholder text).
- Truncate extracted text to a reasonable cap (e.g. ~3000 characters) before passing to the prompt, to control token cost — resumes rarely need more than this for signal extraction (skills, titles, tech stack, years of experience).

---

## 6. Prompt Construction (`prompt_builder.py`)

**Critical rule: conditional sections.** If `resume_text` is `None`, do not include a "Resume: None" line anywhere — omit the entire resume block from the prompt. Same for `job_description`. Sending empty/placeholder fields wastes tokens and can confuse the model into treating absence as a data quality issue rather than an expected variant.

### System Prompt (fixed instructions + KB injected once)

```text
You are an expert technical interviewer and question designer. You generate high-quality, realistic interview questions for a given domain and seniority level, grounded in the reference knowledge base provided below. You do not answer the questions yourself — you only generate them.

KNOWLEDGE BASE (domain: {domain}):
Format per line: TopicName||subtopics (semicolon-separated)||E:easy pattern||M:medium pattern||T:tough pattern.
Use the subtopics as factual grounding for what the question should be about.
Use the E/M/T examples only as a STYLE PATTERN for that difficulty level — never copy them verbatim into your output.

{kb_slice}

DIFFICULTY CALIBRATION:
- easy = definitional, "what is X", basic usage. Tests if the candidate has touched the concept.
- medium = applied, "how would you", compare/contrast, debug-a-scenario. Tests hands-on experience.
- tough = system design, trade-off analysis, edge cases, "why does X fail when Y", optimization at scale. Tests depth and production experience.

SCORING RULE:
For every question you generate, also output a "score" between 0 and 1, representing how relevant that question is to the candidate's profile — combining: (a) fit to the requested domain and difficulty level, and (b) if resume or job description content is given below, how well the question targets that specific candidate's background and the role's requirements. If no resume/job description is given, score purely on fit to domain + difficulty + knowledge base relevance. Higher score = more targeted and relevant; do not default every score to the same value — vary it meaningfully based on actual fit.

OUTPUT RULES:
- Output ONLY valid JSON, no markdown fences, no preamble, no explanation.
- Output schema: {{"questions": [{{"question": "<string>", "score": <float 0-1>}}, ...]}}
- Generate EXACTLY {num_questions} questions.
- All questions must be at difficulty level: {difficulty}.
- Do not repeat the same topic more than twice across the set unless the knowledge base is too narrow to avoid it.
- Questions must be answerable in a spoken interview (no questions requiring a whiteboard/diagram unless the topic explicitly calls for system design discussion).
```

### Human Prompt (per-request variable content, conditional blocks)

```text
Generate {num_questions} {difficulty}-level interview questions for the domain "{domain}".

{resume_block}

{job_description_block}

Return the JSON now.
```

Where:
- `resume_block` = `"CANDIDATE RESUME (extracted text):\n{resume_text}"` if resume was provided, else `""` (empty string, not included at all).
- `job_description_block` = `"JOB DESCRIPTION:\n{job_description}"` if provided, else `""`.
- If BOTH are empty, the human prompt is just the first line + "Return the JSON now." — no dangling blank sections.

> Implementation note: build the human prompt by appending only the non-empty blocks, joined by `\n\n` — do not use `.format()` with possibly-empty named blocks left as literal empty lines stacked up. Strip extra blank lines before sending.

---

## 7. LangChain Implementation (`chain.py`)

Use LangChain's `ChatOpenAI` with `model="gpt-4o"`, low-to-moderate temperature (e.g. `0.4–0.6` — enough variation in question phrasing without drifting off-topic), and structured output enforcement.

**Recommended approach: use `with_structured_output()` (Pydantic schema) rather than asking the model to "output JSON" in free text and parsing it yourself.** This is faster and more reliable than a `JsonOutputParser` retry loop, because the OpenAI structured output / function-calling path enforces the schema at generation time rather than after the fact.

```python
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from typing import List

class QuestionItem(BaseModel):
    question: str = Field(description="The interview question text")
    score: float = Field(description="Relevance score between 0 and 1", ge=0.0, le=1.0)

class QuestionSet(BaseModel):
    questions: List[QuestionItem]

llm = ChatOpenAI(model="gpt-4o", temperature=0.5)
structured_llm = llm.with_structured_output(QuestionSet)

# single call:
result = structured_llm.invoke([
    ("system", system_prompt),
    ("human", human_prompt),
])
# result is already a validated QuestionSet object — no manual JSON parsing needed
```

This also means `prompt_builder.py` should NOT need to instruct "output only valid JSON" as strictly, since `with_structured_output` handles schema enforcement via OpenAI's native structured output / tool-calling — but keep the instruction in the system prompt anyway as a redundant safety net in case of model/library fallback behavior.

---

## 8. Endpoint (`main.py`)

```python
from fastapi import FastAPI, UploadFile, Form, File
from typing import Optional

app = FastAPI()

@app.post("/generate-questions")
async def generate_questions(
    domain: str = Form(...),
    intensity: str = Form(...),
    interview_id: str = Form(...),
    round_type: str = Form(...),
    job_description: Optional[str] = Form(None),
    resume: Optional[UploadFile] = File(None),
):
    # 1. validate domain/intensity/round_type against allowed enums (config.py maps)
    # 2. extract resume text locally if resume provided (document_extract.py) -> resume_text or None
    # 3. load kb slice for domain (kb_loader.py)
    # 4. map intensity -> difficulty, round_type -> num_questions (config.py)
    # 5. build system + human prompt (prompt_builder.py), conditional blocks
    # 6. single call via chain.py -> QuestionSet
    # 7. inject interview_id into final response dict
    # 8. return {"interview_id": interview_id, "questions": [q.dict() for q in result.questions]}
```

---

## 9. Latency Notes (why this design is fast)

1. **One LLM call only.** No separate extraction call, no separate scoring call — extraction-then-grounding happens as ordered instructions inside a single prompt, not as separate round-trips.
2. **KB is pre-sliced by domain at the file level**, not the full 6-category KB sent every time — only the relevant ~1,500–2,000 token slice enters the prompt.
3. **Document extraction is local and synchronous** (`pypdf`/`python-docx`), not an LLM operation — near-zero latency cost.
4. **Conditional prompt blocks** mean requests without resume/JD send a meaningfully smaller prompt — faster for the common case for example warm-up rounds with no resume.
5. **Structured output via `with_structured_output()`** avoids a parse-fail-retry loop that free-form JSON prompting can sometimes trigger.
6. **`interview_id` pass-through in code**, not LLM-generated — saves the model from doing any work on a field it doesn't need to reason about.

---

## 10. requirements.txt (suggested)

```
fastapi
uvicorn
langchain
langchain-openai
pydantic
pypdf
python-docx
python-multipart
python-dotenv
```

---

## 11. Open items to decide while building (not blocking, but worth a comment in code)

- Exact `num_questions` values (6/10/15) are reasonable midpoints of your stated ranges — adjust `QUESTION_COUNT_MAP` in `config.py` if you want different exact numbers.
- Resume text truncation cap (3000 chars) is a starting point — raise if resumes are getting cut off before relevant info, lower if latency from longer prompts becomes noticeable.
- Temperature (0.5) balances variety vs on-topic consistency — lower it (e.g. 0.3) if questions start drifting off-script, raise it if questions feel repetitive across calls.
