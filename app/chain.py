"""LangChain wiring: a single ChatOpenAI call with structured output.

One LLM call per request (spec core principle). with_structured_output enforces
the QuestionSet schema at generation time, avoiding a parse-fail-retry loop.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import OPENAI_MODEL, OPENAI_TEMPERATURE
from app.schemas import QuestionSet


@lru_cache(maxsize=1)
def _get_structured_llm():
    """Build the structured LLM once and reuse it across requests."""
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=OPENAI_TEMPERATURE)
    return llm.with_structured_output(QuestionSet)


def generate_question_set(system_prompt: str, human_prompt: str) -> QuestionSet:
    """Single LLM call -> validated QuestionSet (no manual JSON parsing)."""
    structured_llm = _get_structured_llm()
    result = structured_llm.invoke(
        [
            ("system", system_prompt),
            ("human", human_prompt),
        ]
    )
    return result
