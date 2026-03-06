import os
import redis
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from uvicorn import run

from datetime import datetime, timedelta
from collections import defaultdict

from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from urllib.parse import urlsplit

app = FastAPI()#root_path="/cams")

# load templates folder
env = Environment(loader=FileSystemLoader("templates"))

# Mount shared volume for images and timelapses
app.mount("/static", StaticFiles(directory="/shared_volume"), name="static")

# static files
app.mount("/resources", StaticFiles(directory="resources"), name="resources")
app.mount("/scripts", StaticFiles(directory="scripts"), name="scripts")
app.mount("/styles", StaticFiles(directory="styles"), name="styles")
# templates folder
templates = Jinja2Templates(directory="templates")

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
    full_name: str
    state: str
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

@app.get("/", response_class=HTMLResponse)
def get_home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

# camera api just to check returns on browser
# @app.get("/api/cameras", response_model=List[CameraResponse])
def get_list(request: Request):
    base = str(request.base_url).rstrip("/")

    cameradetails = get_opencast_cameras()
    agents = cameradetails["cameras"]["agents"]["agent"]   # ← 115 items

    camera_list = []

    cainfo = get_opencast_cainfo()
    camera_name_map = cainfo.get("cameras", {})

    capture_status = get_capture_agent_status()
    agent_status = capture_status["capture_agent_status"]["results"]

    # camera status
    activity_map = get_camera_activity_map()
    enriched_cameras = []

    ca_state_map = {
        ca["Name"]: normalize_agent_status(ca.get("Status"))
        for ca in agent_status
    }
    # camera status
    agent_state_map = {
        agent["name"]: agent.get("state", "unknown")
        for agent in agents
        }

    for camera in cameras:

        name = camera["name"]

        camera_list.append({
            "name": name,
            "capture_status": ca_state_map.get(name, "unknown"),
            "current": str(request.url_for("get_latest_image", camera_name=name)),
            "image_url": get_image_url(name, request),
            "image_log": get_logfile(name, "images", request),
            "thumbnail": get_thumbnail(name, "images", request),
            "timelapse": str(request.url_for("get_timelapse", camera_name=name)),
            "timelapse_webm_url": get_timelapse_url(name, "webm", request),
            "timelapse_webm_url_only": get_timelapse_url_only(name, "webm", request),
            "timelapse_mp4_url": get_timelapse_url(name, "mp4", request),
            "timelapse_thumb_url": get_timelapse_url(name, "jpg", request),
            "timelapse_log": get_logfile(name, "timelapse", request),
            "last_capture_completed": redis_client.get(f"camera:{name}:last_capture_completed"),
            "last_capture_attempt": redis_client.get(f"camera:{name}:last_capture_attempt"),
            "last_timelapse_run": redis_client.get(f"camera:{name}:last_timelapse_run"),
            "full_name": camera_name_map.get(name),
            "images": get_camera_images(name, request),
            "camera_status": activity_map.get(name, "offline"),
        })

    return camera_list

# Opencast -------------------------------------------------
@app.get("/opencast/cameras")
def get_opencast_cameras():
    try:
        response = settings.OC.get_cameras()
        cameras_data = response.json()
        return {
            'status': 'success',
            'cameras': cameras_data,
            'helpdesk_email': settings.CONTACT_EMAIL
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ca-full-info")
def get_opencast_cainfo():
    try:
        response = settings.OC.get_cainfo()
        cainfo = response.json()
        return {
            'status': 'success',
            'cameras': cainfo
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# capture agent status
@app.get("/api/capture-agents-status")
def get_capture_agent_status():
    try:
        response = settings.OC.get_capture_agent_status()
        status_data = response.json()
        return {
            'status': 'success',
            'capture_agent_status': status_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# camera events
@app.get("/api/events")
def get_events():
    try:
        response = settings.OC.get_recordings()
        # events_data = response.json()


        return {
            'status': 'success',
            'events': response
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# capture agent differences
@app.get("/api/offline-capture-agents")
def get_offline_capture_agents():
    offline_agents = get_offline_capture_agent_list()
    return {
        "status": "success",
        "count": len(offline_agents),
        "results": offline_agents
    }

def get_offline_capture_agent_list():
    response = settings.OC.get_capture_agent_status()
    data = response.json()

    return [
        agent
        for agent in data.get("results", [])
        if agent.get("Status", "").upper() == "AGENTS.STATUS.OFFLINE"
    ]

# Camera sorting functions ---------------------------------------
def normalize_agent_status(status: str) -> str:
    if not status:
        return "unknown"
    return status.split(".")[-1].lower()

def build_agent_status_map(capture_status):
    results = capture_status.get("capture_agent_status", {}).get("results", [])
    return {
        r["Name"]: normalize_agent_status(r.get("Status"))
        for r in results
    }

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
        return Path(settings.TIMELAPSE_DIR) / f"image_not_found_uct.png"
    return request.url_for(
    "static",
    path=f"timelapse/camera_{camera_name}.{type}"
)

# get timelapse url without request
def get_timelapse_url_only(camera_name: str, file_type: str, request: Request) -> str:
    """
    Returns the relative URL path (no scheme or host) for a timelapse video.
    """
    timelapse_path = Path(settings.TIMELAPSE_DIR) / f"camera_{camera_name}.{file_type}"

    if not timelapse_path.exists():
        return request.url_for(
    "static",
    path=f"timelapse/image_not_found_uct.png")

        # return Path(settings.TIMELAPSE_DIR) / f"image_not_found_uct.png"
        # return "Timelapse not found"

    # Construct the full URL (assuming it's served via STATIC / TIMELAPSE route)
    full_url = f"{request.base_url}static/timelapse/camera_{camera_name}.{file_type}"

    # Strip host, return only the path + query/hash if present
    return urlsplit(full_url).path

def get_thumbnail(camera_name: str, type:str, request: Request) -> str:
    thumbfile = f"/shared_volume/{type}/{camera_name}_thumb.jpg"
    if not os.path.exists(thumbfile):
        return request.url_for(
            "static",
            path=f"timelapse/image_not_found_uct.png")
        # return "Thumbnail not found"
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

# get timelaps image
def get_camera_images(camera_name: str, request: Request):
    img_dir = Path(settings.IMAGE_DIR) / f"camera_{camera_name}"
    if not img_dir.exists():
        return []

    return [
        str(
            request.url_for(
                "static",
                path=f"images/camera_{camera_name}/{img.name}"
            )
        )
        for img in sorted(img_dir.glob("*.jpg"))
    ]

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
    """Return counts and lists of online/offline cameras based on `last_capture_completed`.

    A camera is considered *active* if its `last_capture_completed` timestamp is within
    `threshold_seconds`. By default `threshold_seconds` is 2 * CAPTURE_INTERVAL.
    """
    if threshold_seconds is None:
        threshold_seconds = settings.CAPTURE_INTERVAL * 2

    now = datetime.now()
    online = []
    offline = []
    timestamps = {}

    for ca in cameras:
        key = f"camera:{ca['name']}:last_capture_completed"
        ts = redis_client.get(key)
        timestamps[ca['name']] = ts
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                if (now - t).total_seconds() <= threshold_seconds:
                    online.append(ca['name'])
                else:
                    offline.append(ca['name'])
            except Exception:
                # Malformed timestamp -> treat as offline
                offline.append(ca['name'])
        else:
            # No timestamp -> offline
            offline.append(ca['name'])

    return {
        "threshold_seconds": threshold_seconds,
        "online_count": len(online),
        "offline_count": len(offline),
        "online": online,
        "offline": offline,
        "last_capture_completed": timestamps
    }

# get the active offline camera
def get_camera_activity_map(threshold_seconds: Optional[int] = None):
    if threshold_seconds is None:
        threshold_seconds = settings.CAPTURE_INTERVAL * 3

    now = datetime.now()
    activity_map = {}

    for ca in cameras:
        name = ca["name"]
        key = f"camera:{name}:last_capture_completed"
        ts = redis_client.get(key)

        status = "offline"

        if ts:
            try:
                t = datetime.fromisoformat(ts)
                if (now - t).total_seconds() <= threshold_seconds:
                    status = "online"
            except Exception:
                status = "offline"

        activity_map[name] = status

    return activity_map

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