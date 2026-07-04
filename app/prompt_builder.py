"""Builds the system + human prompt for the single LLM call.

Critical rule (spec section 6): conditional sections. If resume_text or
job_description is absent, the entire block is omitted — no placeholder lines.
"""

from typing import Optional, Tuple

SYSTEM_TEMPLATE = """You are an expert technical interviewer and question designer. You generate high-quality, realistic interview questions for a given domain and seniority level, grounded in the reference knowledge base provided below. You do not answer the questions yourself — you only generate them.

KNOWLEDGE BASE (domain: {domain}):
Format per line: TopicName||subtopics (semicolon-separated)||E:easy pattern||M:medium pattern||T:tough pattern.
Use the subtopics as factual grounding for what the question should be about.
Use the E/M/T examples only as a STYLE PATTERN for that difficulty level — never copy them verbatim into your output.

{kb_slice}

DIFFICULTY CALIBRATION:
- easy = definitional, "what is X", basic usage. Tests if the candidate has touched the concept.
- medium = applied, "how would you", compare/contrast, debug-a-scenario. Tests hands-on experience.
- tough = system design, trade-off analysis, edge cases, "why does X fail when Y", optimization at scale. Tests depth and production experience.

PERSONALIZATION / TARGETING RULE:
If a CANDIDATE RESUME and/or JOB DESCRIPTION is provided below, you MUST use it to shape the ACTUAL QUESTIONS — not just their scores:
- Prioritize knowledge-base topics that match the specific tools, frameworks, projects, and responsibilities named in the resume/JD. Spend most of the question set on those areas.
- Where it reads naturally, phrase questions around the candidate's real stack and experience (e.g. reference the specific technologies, model types, or deployment targets they list) instead of generic phrasing — while still keeping every question grounded in a knowledge-base topic and at the requested difficulty.
- Even at easy difficulty, choose WHICH definitional topics to ask based on what the resume/JD emphasizes.
- Do not ask about areas the resume/JD explicitly excludes or clearly has no bearing on, unless the knowledge base is too narrow to fill the set otherwise.
- If NO resume/JD is provided, cover the domain broadly and representatively at the requested difficulty.

SCORING RULE:
For every question you generate, also output a "score" between 0 and 1, representing how relevant that question is to the candidate's profile — combining: (a) fit to the requested domain and difficulty level, and (b) if resume or job description content is given below, how well the question targets that specific candidate's background and the role's requirements. If no resume/job description is given, score purely on fit to domain + difficulty + knowledge base relevance.

Use the FULL 0-1 range and produce a genuine spread — do NOT cluster scores near 1.0. Score anchors:
- 0.90-1.00: reserve for questions that hit a core, explicitly-stated skill in the resume/JD (or, with no resume/JD, the single most central topic of the domain at this difficulty). At most a few questions should land here.
- 0.70-0.89: solidly on-topic and clearly relevant, but a step removed from the candidate's strongest stated experience or the role's primary focus.
- 0.50-0.69: relevant to the domain but peripheral to this candidate/role, or a topic only weakly supported by the resume/JD.
- below 0.50: tangential, or testing an area the resume explicitly lacks or the JD does not call for.
Vary scores meaningfully across the set — two questions should rarely share the exact same score, and a realistic set spans a visible range rather than all sitting at the top.

OUTPUT RULES:
- Output ONLY valid JSON, no markdown fences, no preamble, no explanation.
- Output schema: {{"questions": [{{"question": "<string>", "score": <float 0-1>}}, ...]}}
- Generate EXACTLY {num_questions} questions.
- All questions must be at difficulty level: {difficulty}.
- Do not repeat the same topic more than twice across the set unless the knowledge base is too narrow to avoid it.
- Questions must be answerable in a spoken interview (no questions requiring a whiteboard/diagram unless the topic explicitly calls for system design discussion)."""


def build_prompts(
    domain: str,
    difficulty: str,
    num_questions: int,
    kb_slice: str,
    resume_text: Optional[str] = None,
    job_description: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (system_prompt, human_prompt).

    The human prompt is assembled from only the non-empty blocks, joined by
    blank lines — no dangling empty sections (spec section 6 implementation note).
    """
    system_prompt = SYSTEM_TEMPLATE.format(
        domain=domain,
        kb_slice=kb_slice,
        num_questions=num_questions,
        difficulty=difficulty,
    )

    blocks = [
        f'Generate {num_questions} {difficulty}-level interview questions for the domain "{domain}".'
    ]

    if resume_text:
        blocks.append(f"CANDIDATE RESUME (extracted text):\n{resume_text}")

    if job_description:
        blocks.append(f"JOB DESCRIPTION:\n{job_description}")

    # When any candidate context is present, explicitly instruct tailoring so
    # personalization is reliable across all difficulty levels (not emergent).
    if resume_text or job_description:
        blocks.append(
            "Tailor the questions to the candidate context above: prioritize the "
            "specific technologies, projects, and responsibilities it names, and "
            "phrase questions around them where natural, per the "
            "PERSONALIZATION / TARGETING RULE."
        )

    blocks.append("Return the JSON now.")

    human_prompt = "\n\n".join(block.strip() for block in blocks if block.strip())

    return system_prompt, human_prompt
