from typing import Any, Literal

from pydantic import BaseModel

from app.base.contracts import ContractModel


class ErrorEnvelope(ContractModel):
    success: Literal[False] = False
    error: str


class SuccessEnvelope(ContractModel):
    success: Literal[True] = True


def body(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
