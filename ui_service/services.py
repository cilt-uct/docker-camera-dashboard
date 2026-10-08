import asyncio
import hashlib
import json

from fastapi import Request, HTTPException
from datetime import datetime

from utils.settings import logger
from core import settings, redis_client
from models import CameraResponse, CameraResponseMinimal, CaptureAgent
from files import get_image_url, get_timelapse_url, get_thumbnail

async def ensure_camera_exists(camera_name: str):
    exists = await redis_client.exists(f"camera:{camera_name}")
    if not exists:
        raise HTTPException(status_code=404, detail="Camera not found")

def generate_etag(data: dict) -> str:
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]

def get_camera_status(last_capture_completed:str) -> str:
    if not last_capture_completed:
        return "offline"

    try:
        now = datetime.now().astimezone()
        t = datetime.fromisoformat(last_capture_completed)

        return "online" if (now - t).total_seconds() <= settings.STATUS_INTERVAL else "offline"
    except Exception as e:
        logger.error(f'{last_capture_completed} : {e}')
        return "offline"

async def build_camera(name: str, request: Request, display_names: dict, full: bool, semaphore: asyncio.Semaphore):
    async with semaphore:
        cam_hash = await redis_client.hgetall(f"camera:{name}")
        if not cam_hash:
            return None

        state = get_camera_status(cam_hash.get("last_capture_completed"))

        if full:
            (
                image_url,
                # image_log,
                thumbnail,
                # timelapse_webm,
                # timelapse_mp4,
                # timelapse_thumb,
                # timelapse_log
            ) = await asyncio.gather(
                get_image_url(name, request),
                # get_logfile(name, "images", request),
                get_thumbnail(name, "images", request),
                # get_timelapse_url(name, "webm", request),
                # get_timelapse_url(name, "mp4", request),
                # get_timelapse_url(name, "jpg", request),
                # get_logfile(name, "timelapse", request),
            )

            return CameraResponse(
                name=cam_hash.get("name", ""),
                fullname=display_names.get(name, name),
                state=state,
                current=str(request.url_for("get_latest_image", camera_name=name)),
                image_url=image_url,
                # image_log=image_log,
                thumbnail=thumbnail,
                # timelapse=str(request.url_for("get_timelapse", camera_name=name)),
                # timelapse_webm_url=timelapse_webm,
                # timelapse_mp4_url=timelapse_mp4,
                # timelapse_thumb_url=timelapse_thumb,
                # timelapse_log=timelapse_log,
                last_capture_completed=cam_hash.get("last_capture_completed"),
                last_capture_attempt=cam_hash.get("last_capture_attempt"),
                last_timelapse_run=cam_hash.get("last_timelapse_run"),
            )

        else:
            # minimal version (still async-safe)
            return CameraResponseMinimal(
                name=cam_hash.get("name", ""),
                fullname=display_names.get(name, name),
                state=state,
                last_capture_completed=cam_hash.get("last_capture_completed"),
                last_capture_attempt=cam_hash.get("last_capture_attempt"),
                last_timelapse_run=cam_hash.get("last_timelapse_run"),
            )

# We are possibly accessing the filesystem so IO will be done concurrently in batches of 25
async def fetch_cameras(request: Request, full: bool = True):
    camera_names = await redis_client.smembers("camera:index")
    display_names = await redis_client.hgetall("ca:display")

    semaphore = asyncio.Semaphore(25) # batches of 25

    tasks = [
        build_camera(name, request, display_names, full, semaphore)
        for name in camera_names
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    cameras = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Camera build failed: {r}")
            continue
        if r:
            cameras.append(r)

    # remove None results (missing cameras)
    cameras = [cam for cam in cameras if cam is not None]

    return cameras

async def fetch_agents():
    """Get all capture agent details from Redis as a list of dicts."""
    agent_names = await redis_client.smembers("ca:index")
    agents = []

    for name in agent_names:
        agent_hash = await redis_client.hgetall(f"ca:{name}")
        if not agent_hash:
            continue

        agents.append(CaptureAgent(
                name=name,
                display=agent_hash.get("display", ""),
                state=agent_hash.get("state", ""),
                time_since_last_update=int(agent_hash.get("time_since_last_update", 0)),
                last_updated=agent_hash.get("last_updated")
            ))

    return agents

async def fetch_schedule() -> dict:
    """Get today's schedule from Redis, adding the current camera state per location."""
    raw = await redis_client.get("schedule:today")
    if not raw:
        return {"date": None, "window_start": None, "window_end": None,
                "last_refresh": None, "total": 0, "locations": []}

    schedule = json.loads(raw)
    for loc in schedule.get("locations", []):
        if not loc.get("has_camera"):
            loc["camera_state"] = "none"
            continue

        # Use the live camera hash so the state is fresher than the stored schedule
        last_completed = await redis_client.hget(f"camera:{loc['name']}", "last_capture_completed")
        loc["camera_last_capture_completed"] = last_completed or loc.get("camera_last_capture_completed")
        loc["camera_state"] = get_camera_status(loc["camera_last_capture_completed"])

    return schedule

async def fetch_pyca() -> dict:
    """Get the PyCA's from Redis."""
    raw = await redis_client.smembers("pyca:index")
    if not raw:
        return {}

    pyca_index = list(raw)
    result = []
    for name in pyca_index:
        pyca_hash = await redis_client.hgetall(f"pyca:{name}")
        result.append({
            "name": name,
            "url": pyca_hash.get("url") if bool(pyca_hash) else None,
            "state": pyca_hash.get("state") or "none",
            "last_updated": pyca_hash.get("last_updated") or None
        })

    return {'index': pyca_index, 'list': result}

async def get_camera_current(camera_name: str, request: Request):
    image_url, thumb_url = await asyncio.gather(
        get_image_url(camera_name, request),
        get_thumbnail(camera_name, "images", request)
    )

    return {
        "image_url": image_url,
        "thumb_url": thumb_url
    }

async def get_camera_timelapse(camera_name: str, request: Request):
    webm, mp4, thumb = await asyncio.gather(
        get_timelapse_url(camera_name, 'webm', request),
        get_timelapse_url(camera_name, 'mp4', request),
        get_timelapse_url(camera_name, 'jpg', request)
    )

    return {
        "webm_url": webm,
        "mp4_url": mp4,
        "thumb_url": thumb
    }
