from pydantic import BaseModel
from typing import Optional

# Model for response
class CameraResponse(BaseModel):
    name: str
    fullname: str
    state: str
    current: str
    image_url: Optional[str] = None
    # image_log: Optional[str] = None
    thumbnail: Optional[str] = None
    # timelapse: Optional[str] = None
    # timelapse_webm_url: Optional[str] = None
    # timelapse_mp4_url: Optional[str] = None
    # timelapse_thumb_url: Optional[str] = None
    # timelapse_log: Optional[str] = None
    # Timestamps — may be None if never set
    last_capture_completed: Optional[str] = None
    last_capture_attempt: Optional[str] = None
    last_timelapse_run: Optional[str] = None

class CameraResponseMinimal(BaseModel):
    name: str
    fullname: str
    state: str
    # Timestamps — may be None if never set
    last_capture_completed: Optional[str] = None
    last_capture_attempt: Optional[str] = None
    last_timelapse_run: Optional[str] = None

class CaptureAgent(BaseModel):
    name: str
    display: str
    state: str
    # Timestamps — may be None if never set
    time_since_last_update: Optional[int] = None
    last_updated: Optional[str] = None

class CameraCurrentResponse(BaseModel):
    image_url: str | None
    thumb_url: str | None


class CameraTimelapseResponse(BaseModel):
    webm_url: str | None
    mp4_url: str | None
    thumb_url: str | None
