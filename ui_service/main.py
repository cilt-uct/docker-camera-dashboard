import os
import redis

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from uvicorn import run

from datetime import datetime, timedelta

from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()#root_path="/cams")

# Mount shared volume for images and timelapses
app.mount("/static", StaticFiles(directory="/shared_volume"), name="static")

# Configuration
from utils.settings import FetchSettings, logger, cameras
settings = FetchSettings()
settings.TITLE = "Display Camera Images Service"

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True
)

# Bridge uvicorn error logs for parse issues into our main logger with more context
import logging

class UvicornParseErrorHandler(logging.Handler):
    """Re-logs uvicorn parse errors (e.g., invalid HTTP requests) with extra context."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if "Invalid HTTP request received" in msg:
                client = getattr(record, 'client_addr', None) or getattr(record, 'addr', None)
                if client:
                    logger.warning(f"[HTTP PARSE ERROR] {msg} client={client}", exc_info=record.exc_info)
                else:
                    logger.warning(f"[HTTP PARSE ERROR] {msg}", exc_info=record.exc_info)
        except Exception:
            # Never let logging failures crash the app
            pass

def _attach_uvicorn_parse_handler():
    try:
        uv_err = logging.getLogger("uvicorn.error")
        uv_err.setLevel(logging.DEBUG)
        uv_err.addHandler(UvicornParseErrorHandler())
    except Exception:
        pass

# Attach the handler early so uvicorn warnings are forwarded to our logger
_attach_uvicorn_parse_handler()

# Database model (simplified)
class Camera(BaseModel):
    name: str
    rtsp_url: str

# Model for response (excluding rtsp_url)
class CameraResponse(BaseModel):
    name: str
    current: str
    image_url: str
    image_log: str
    thumbnail: str
    timelapse: str
    timelapse_webm_url: str
    timelapse_mp4_url: str
    timelapse_thumb_url: str
    timelapse_log: str
    # Timestamps (ISO) pulled from Redis — may be None if never set
    last_capture_completed: Optional[str] = None
    last_capture_attempt: Optional[str] = None
    last_timelapse_run: Optional[str] = None

@app.get("/", response_model=List[CameraResponse])
def get_list(request: Request):
    return [
            {
                "name": camera["name"],
                "current": str(request.url_for('get_latest_image', camera_name=camera["name"])),
                "image_url": get_image_url(camera["name"], request),
                "image_log": get_logfile(camera["name"], "images", request),
                "thumbnail": get_thumbnail(camera["name"], "images", request),
                "timelapse": str(request.url_for('get_timelapse', camera_name=camera["name"])),
                "timelapse_webm_url": get_timelapse_url(camera["name"], 'webm', request),
                "timelapse_mp4_url": get_timelapse_url(camera["name"], 'mp4', request),
                "timelapse_thumb_url": get_timelapse_url(camera["name"], 'jpg',request),
                "timelapse_log": get_logfile(camera["name"], "timelapse", request),
                "last_capture_completed": redis_client.get(f"camera:{camera['name']}:last_capture_completed"),
                "last_capture_attempt": redis_client.get(f"camera:{camera['name']}:last_capture_attempt"),
                "last_timelapse_run": redis_client.get(f"camera:{camera['name']}:last_timelapse_run"),
            }
            for camera in cameras
        ]

# Opencast -------------------------------------------------
@app.get("/opencast/cameras")
def get_opencast_cameras():
    try:
        response = settings.OC.get_cameras()
        cameras_data = response.json()
        return {
            'status': 'success',
            'cameras': cameras_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Cameras ---------------------------------------------------

def get_image_url(camera_name: str, request: Request) -> str:
    image_dir = Path(settings.IMAGE_DIR) / f"camera_{camera_name}"
    if not image_dir.exists():
        return "Camera Image not found"
    if not any(image_dir.iterdir()):
        return "No images found"

    latest_image = max(image_dir.iterdir())
    logger.debug(f'{latest_image.name} {type(latest_image)}')
    return str(request.url_for("static", path=f"images/camera_{camera_name}/{latest_image.name}"))

def get_timelapse_url(camera_name: str, type:str, request: Request) -> str:
    timelapse_path = Path(settings.TIMELAPSE_DIR) / f"camera_{camera_name}.{type}"
    if not timelapse_path.exists():
        return "Timelapse not found"
    return str(request.url_for("static", path=f"timelapse/camera_{camera_name}.{type}"))

def get_thumbnail(camera_name: str, type:str, request: Request) -> str:
    thumbfile = f"/shared_volume/{type}/{camera_name}_thumb.jpg"
    if not os.path.exists(thumbfile):
        return "Thumbnail not found"
    return str(request.url_for("static", path=f"{type}/{camera_name}_thumb.jpg"))

def get_logfile(camera_name: str, type:str, request: Request) -> str:
    logfile = f"/shared_volume/{type}/{camera_name}.log"
    if not os.path.exists(logfile):
        return "Logfile not found"
    return str(request.url_for("static", path=f"{type}/{camera_name}.log"))

@app.get("/{camera_name}/current")
def get_latest_image(camera_name: str, request: Request):
    return {
        "image_url": get_image_url(camera_name, request),
        "thumb_url": get_thumbnail(camera_name, "images", request)
    }

@app.get("/{camera_name}/timelapse")
def get_timelapse(camera_name: str, request: Request):
    return {
        "webm_url": get_timelapse_url(camera_name, 'webm', request),
        "mp4_url": get_timelapse_url(camera_name, 'mp4', request),
        "thumb_url": get_timelapse_url(camera_name, 'jpg',request)
    }

# Status ----------------------------------------------------
@app.get("/status")
def get_status(request: Request):
    return {
        "service": settings.TITLE,
        "version": settings.VERSION,
        "environment": settings.SERVER_TYPE,
        "debug": settings.SERVER_DEBUG,
        "running_in_docker": settings.SERVER_IN_DOCKER,
        "scheduler_service_start" : redis_client.get("scheduler_service_start"),
        "ui_service_start": redis_client.get("ui_service_start"),
        "activity": str(request.url_for('get_cameras_activity'))
    }

@app.get("/activity")
def get_cameras_activity(threshold_seconds: Optional[int] = None):
    """Return counts and lists of active/inactive cameras based on `last_capture_completed`.

    A camera is considered *active* if its `last_capture_completed` timestamp is within
    `threshold_seconds`. By default `threshold_seconds` is 2 * CAPTURE_INTERVAL.
    """
    if threshold_seconds is None:
        threshold_seconds = settings.CAPTURE_INTERVAL * 2

    now = datetime.now()
    active = []
    inactive = []
    timestamps = {}

    for ca in cameras:
        key = f"camera:{ca['name']}:last_capture_completed"
        ts = redis_client.get(key)
        timestamps[ca['name']] = ts
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                if (now - t).total_seconds() <= threshold_seconds:
                    active.append(ca['name'])
                else:
                    inactive.append(ca['name'])
            except Exception:
                # Malformed timestamp -> treat as inactive
                inactive.append(ca['name'])
        else:
            # No timestamp -> inactive
            inactive.append(ca['name'])

    return {
        "threshold_seconds": threshold_seconds,
        "active_count": len(active),
        "inactive_count": len(inactive),
        "active": active,
        "inactive": inactive,
        "last_capture_completed": timestamps
    }

if __name__ == "__main__":

    log_level = 'debug' if settings.SERVER_DEBUG else 'info'

    start_time = datetime.now().isoformat()
    redis_client.set('ui_service_start', start_time)
    logger.info(f"UI starting: { start_time}")

    run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level=log_level,
        root_path=settings.ROOT_PATH
    )