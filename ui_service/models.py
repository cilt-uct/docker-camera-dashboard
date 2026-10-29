from pydantic import BaseModel


# Model for response
class CameraResponse(BaseModel):
    name: str
    fullname: str
    state: str
    current: str
    image_url: str | None = None
    # image_log: str | None = None
    thumbnail: str | None = None
    # timelapse: str | None = None
    # timelapse_webm_url: str | None = None
    # timelapse_mp4_url: str | None = None
    # timelapse_thumb_url: str | None = None
    # timelapse_log: str | None = None
    # Timestamps — may be None if never set
    last_capture_completed: str | None = None
    last_capture_attempt: str | None = None
    last_timelapse_run: str | None = None

class CameraResponseMinimal(BaseModel):
    name: str
    fullname: str
    state: str
    # Timestamps — may be None if never set
    last_capture_completed: str | None = None
    last_capture_attempt: str | None = None
    last_timelapse_run: str | None = None

class CaptureAgent(BaseModel):
    name: str
    display: str
    state: str
    # Timestamps — may be None if never set
    time_since_last_update: int | None = None
    last_updated: str | None = None

class CameraCurrentResponse(BaseModel):
    image_url: str | None
    thumb_url: str | None


class CameraTimelapseResponse(BaseModel):
    webm_url: str | None
    mp4_url: str | None
    thumb_url: str | None
