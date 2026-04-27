from typing import Literal, Optional

from pydantic import model_validator

from app.base.contracts import ContractModel


class ActiveTask(ContractModel):
    id: str
    type: Literal["source", "studio", "background"]
    label: str
    detail: str
    status: str
    created_at: Optional[str] = None
    progress: Optional[str] = None


class ActiveTasksResponse(ContractModel):
    success: Literal[True] = True
    tasks: list[ActiveTask]
    count: int

    @model_validator(mode="after")
    def count_matches_tasks(self) -> "ActiveTasksResponse":
        if self.count != len(self.tasks):
            raise ValueError("count must match tasks length")
        return self
