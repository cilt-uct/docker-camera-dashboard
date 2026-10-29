from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CameraBase(BaseModel):
    name: str
    url: str
    enabled: bool = True

class CameraCreate(CameraBase):
    pass

class CameraUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None
    last_capture_attempt: datetime | None = None
    last_capture_completed: datetime | None = None
    last_timelapse_run: datetime | None = None

class CameraResponse(CameraBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_capture_attempt: datetime | None = None
    last_capture_completed: datetime | None = None
    last_timelapse_run: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
