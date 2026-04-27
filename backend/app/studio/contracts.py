from typing import Any, Literal, Optional

from pydantic import ConfigDict, Field

from app.base.contracts import ContractModel


StudioJobStatus = Literal["pending", "processing", "ready", "error", "cancelled"]


class StudioJob(ContractModel):
    model_config = ConfigDict(extra="allow")

    id: str
    project_id: Optional[str] = None
    job_type: Optional[str] = None
    status: StudioJobStatus
    progress: Optional[str] = None
    error: Optional[str] = None
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    direction: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    job_data: dict[str, Any] = Field(default_factory=dict)


class StudioJobResponse(ContractModel):
    success: Literal[True] = True
    job: dict[str, Any]


class StudioEventPayload(ContractModel):
    studio_item: str
    direction: Optional[str] = None
    source_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "processing", "ready", "error", "cancelled"] = "pending"
