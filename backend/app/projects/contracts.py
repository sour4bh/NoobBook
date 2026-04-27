from typing import Literal

from pydantic import model_validator

from app.base.contracts import ContractModel

REQUIRED_COST_MODEL_KEYS = frozenset({"opus", "sonnet", "haiku"})


class CostBucket(ContractModel):
    input_tokens: int
    output_tokens: int
    cost: float


class ProjectCosts(ContractModel):
    total_cost: float
    by_model: dict[str, CostBucket]

    @model_validator(mode="after")
    def require_model_buckets(self) -> "ProjectCosts":
        missing = REQUIRED_COST_MODEL_KEYS.difference(self.by_model)
        if missing:
            raise ValueError(f"missing cost buckets: {', '.join(sorted(missing))}")
        return self


class ProjectCostsResponse(ContractModel):
    success: Literal[True] = True
    costs: ProjectCosts
