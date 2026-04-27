from typing import Literal, Optional

from pydantic import Field

from app.base.contracts import ContractModel


SourceCategory = Literal["document", "audio", "image", "data", "link", "unknown"]
SourceType = Literal["DOCUMENT", "AUDIO", "IMAGE", "DATA", "LINK", "UNKNOWN"]
SourceStatus = Literal["uploaded", "processing", "embedding", "ready", "error", "cancelled"]


class FileInfo(ContractModel):
    extension: str
    category: SourceCategory
    mime_type: str


class SourceRow(ContractModel):
    id: str
    name: str
    type: SourceType
    status: SourceStatus
    project_id: Optional[str] = None
    token_count: Optional[int] = None
    embedding_info: dict = Field(default_factory=dict)


class CitationChunk(ContractModel):
    content: str
    chunk_id: str
    source_id: str
    source_name: str
    page_number: int
    chunk_index: int


class CitationResponse(ContractModel):
    success: Literal[True] = True
    chunk: CitationChunk


class ProcessedContentResponse(ContractModel):
    success: Literal[True] = True
    content: str
    source_name: str


class GeneratedAssetAccess(ContractModel):
    project_id: str
    filename: str
    mime_type: str
