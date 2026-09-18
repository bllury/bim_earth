from typing import Any, Literal, Optional

from pydantic import BaseModel


class ConvertAccepted(BaseModel):
    taskId: str
    projectId: str
    revisionId: str


class ConvertStatus(BaseModel):
    taskId: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: float = 0.0
    message: Optional[str] = None
    tilesetUrl: Optional[str] = None
    metadataUrl: Optional[str] = None
    modelId: Optional[str] = None
    error: Optional[str] = None
    projectId: Optional[str] = None
    revisionId: Optional[str] = None


class RecentModel(BaseModel):
    projectId: str
    projectName: str
    revisionId: str
    fileName: str
    modelId: str
    tilesetUrl: str
    metadataUrl: str
    longitude: float = 0
    latitude: float = 0
    camera: Optional[dict] = None


class CameraState(BaseModel):
    projectId: str
    camera: dict


class ElementBusinessPayload(BaseModel):
    business: dict[str, Any] = {}
