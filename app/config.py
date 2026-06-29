"""Fixed constant maps for the interview question generator.

These are intentionally simple module-level dicts so they're easy to tune later
without touching any business logic (see spec section 2 and section 11).
"""

# intensity -> difficulty calibration used in the prompt
DIFFICULTY_MAP = {
    "intern": "easy",
    "senior": "medium",
    "staff": "tough",
}

# round_type -> exact number of questions to generate.
# Values are reasonable midpoints of the stated ranges; tune freely.
QUESTION_COUNT_MAP = {
    "warm-up": 6,              # range given was 5-7
    "standard-technical": 10,  # range given was 8-12
    "final-round": 15,         # fixed at 15
}

# domain -> knowledge base file. The repo ships per-domain files under
# knowledge-base/ (one line per topic, pipe-delimited).
DOMAIN_TO_KB_FILE = {
    "AI Engineer": "knowledge-base/ai_engineer.txt",
    "Machine Learning": "knowledge-base/machine_learning.txt",
    "Computer Vision": "knowledge-base/computer_vision.txt",
    "MLOps": "knowledge-base/mlops.txt",
    "LLM Systems": "knowledge-base/llm_systems.txt",
    "Behavioral": "knowledge-base/behavioral.txt",
}

# Allowed values for the pass-through interview_id field.
ALLOWED_INTERVIEW_IDS = {"aria", "james", "priya", "patel"}

# Derived sets for fast validation.
ALLOWED_DOMAINS = set(DOMAIN_TO_KB_FILE.keys())
ALLOWED_INTENSITIES = set(DIFFICULTY_MAP.keys())
ALLOWED_ROUND_TYPES = set(QUESTION_COUNT_MAP.keys())

# Resume text truncation cap (chars) before it enters the prompt — controls
# token cost. Raise if resumes get cut off, lower if latency becomes an issue.
RESUME_CHAR_CAP = 3000

# LLM settings.
OPENAI_MODEL = "gpt-4o"
OPENAI_TEMPERATURE = 0.5
