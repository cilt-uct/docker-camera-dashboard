from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class CameraBase(BaseModel):
    name: str
    url: str
    enabled: bool = True

class CameraCreate(CameraBase):
    pass

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None
    last_capture_attempt: Optional[datetime] = None
    last_capture_completed: Optional[datetime] = None
    last_timelapse_run: Optional[datetime] = None

class CameraResponse(CameraBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_capture_attempt: Optional[datetime] = None
    last_capture_completed: Optional[datetime] = None
    last_timelapse_run: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
