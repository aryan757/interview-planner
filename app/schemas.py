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

    user_id: str
    interview_id: str
    questions: List[QuestionItem]


class ConvDimensionScores(BaseModel):
    """Per-dimension percents (0-100) returned by the transcript-scoring LLM."""

    technical: int = Field(ge=0, le=100)
    depth: int = Field(ge=0, le=100)
    communication: int = Field(ge=0, le=100)
    problem_solving: int = Field(ge=0, le=100)


class ConvQuestionReview(BaseModel):
    """One LLM review for a single question/answer pair."""

    percent: int = Field(ge=0, le=100, description="How good this specific answer was")
    good: str = Field(description="One short sentence on what was good")
    improve: str = Field(description="One short sentence on what to improve")


class ConversationScore(BaseModel):
    """Structured output for scoring a saved voice-interview transcript."""

    dimensions: ConvDimensionScores
    question_reviews: List[ConvQuestionReview]


class DimensionBreakdown(BaseModel):
    points: int
    max: int
    percent: int


class EvaluationQuestionReview(BaseModel):
    question: str
    score: int
    max_score: int
    good: str
    improve: str


class EvaluationResponse(BaseModel):
    """Voice interview score report for a user (latest completed session)."""

    user_id: int
    interview_id: str
    topic: str
    interview_type: str
    intensity: str
    interviewer: str
    status: str
    final_score: int
    score_band: str
    score_color: str
    band_label: str
    certified: bool
    xp_earned: int
    dimensions: dict[str, DimensionBreakdown]
    delivery: dict[str, float | int | str]
    question_reviews: List[EvaluationQuestionReview]
    completed_at: str | None = None
    created_at: str | None = None
