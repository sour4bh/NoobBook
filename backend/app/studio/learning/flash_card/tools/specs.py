"""Typed tool specs for this domain-owned tool family."""

from typing import Literal

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class GenerateFlashCardsInputCardsItemModel(ContractModel):
    back: str = Field(description='The back of the card - the answer, definition, or explanation (max 50 words)')
    category: Literal['definition', 'concept', 'application', 'comparison'] = Field(description='The type of flash card')
    front: str = Field(description='The front of the card - a term, question, or prompt (max 15 words)')
class GenerateFlashCardsInput(ContractModel):
    cards: list[GenerateFlashCardsInputCardsItemModel] = Field(description='Array of flash cards to generate', min_length=5, max_length=20)
    topic_summary: str = Field(description='A brief 1-2 sentence summary of what these flash cards cover')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='generate_flash_cards',
        description='Submit generated flash cards. Each card has a front (question/term) and back (answer/definition).',
        input_model=GenerateFlashCardsInput,
        terminates_run=True,
        metadata={'registry_name': 'flash_cards_tool'},
    ),
)
