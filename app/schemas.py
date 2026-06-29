"""Pydantic models for request validation and structured LLM output."""

from typing import List

from pydantic import BaseModel, Field


class QuestionItem(BaseModel):
    """A single generated interview question with its relevance score."""

    question: str = Field(description="The interview question text")
    score: float = Field(
        description="Relevance score between 0 and 1",
        ge=0.0,
        le=1.0,
    )


class QuestionSet(BaseModel):
    """The structured object the LLM returns — only questions, no interview_id.

    interview_id is injected by Python after the call (spec section 3).
    """

    questions: List[QuestionItem]


class GenerateQuestionsResponse(BaseModel):
    """Final API response shape returned to the client."""

    interview_id: str
    questions: List[QuestionItem]
