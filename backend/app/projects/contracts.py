from typing import Any, Literal, Optional

from pydantic import Field

from app.base.contracts import ContractModel


class CostBucket(ContractModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    provider_units: dict[str, Any] = Field(default_factory=dict)
    cost: float


class ProjectCosts(ContractModel):
    total_cost: float
    by_model: dict[str, CostBucket]


class ProjectCostsResponse(ContractModel):
    success: Literal[True] = True
    costs: ProjectCosts
