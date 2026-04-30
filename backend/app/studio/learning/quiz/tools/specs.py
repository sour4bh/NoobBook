"""Typed tool specs for this domain-owned tool family."""

from typing import Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class GenerateQuizInputQuestionsItemModelOptionsItemModel(ContractModel):
    id: str = Field(description="Unique option identifier (e.g., 'a', 'b', 'c', 'd')")
    text: str = Field(description='The option text (max 50 words)')
class GenerateQuizInputQuestionsItemModel(ContractModel):
    correct_answers: list[str] = Field(description='Array of correct option IDs. Single item for single-select, multiple items for multi-select.', min_length=1)
    explanation: str = Field(description='Explanation shown after answering, explaining why the answer is correct (max 75 words)')
    hint: Optional[str] = Field(default=None, description='Optional hint to help the user (max 30 words). Leave empty string if no hint needed.')
    id: str = Field(description="Unique identifier for this question (e.g., 'q1', 'q2')")
    is_multi_select: bool = Field(description='True if multiple answers should be selected, false for single-select')
    options: list[GenerateQuizInputQuestionsItemModelOptionsItemModel] = Field(description='Array of answer options (2-6 options)', min_length=2, max_length=6)
    question: str = Field(description='The question text (clear, concise, max 100 words)')
class GenerateQuizInput(ContractModel):
    questions: list[GenerateQuizInputQuestionsItemModel] = Field(description='Array of quiz questions', min_length=5, max_length=25)
    topic_summary: str = Field(description='A brief 1-2 sentence summary of what this quiz covers')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='generate_quiz',
        description='Submit a quiz with multiple choice questions. Each question has options, correct answer(s), optional hint, and explanation.',
        input_model=GenerateQuizInput,
        terminates_run=True,
        metadata={'registry_name': 'quiz_tool'},
    ),
)
