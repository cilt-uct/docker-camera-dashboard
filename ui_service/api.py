from fastapi import APIRouter, Request, Response, HTTPException
from typing import List, Dict

from utils.settings import logger
from core import settings, redis_client
from models import CameraCurrentResponse, CameraTimelapseResponse
from services import (
    ensure_camera_exists, generate_etag,
    get_camera_current, get_camera_timelapse,
    fetch_cameras, fetch_agents
)

router = APIRouter()

# Cameras ---------------------------------------------------
@router.get("/api/cameras")
async def get_cameras(request: Request, response: Response):
    try:
        cameras = await fetch_cameras(request, full=True)

        payload = [c.model_dump() for c in cameras]
        etag = generate_etag(payload)
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = "no-cache, must-revalidate"

        return {
            "status": "success",
            "cameras": payload,
            "total": len(payload),
            "version": etag
        }

    except Exception as e:
        logger.exception("Failed to get cameras")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/camera/{camera_name}/current", response_model=CameraCurrentResponse)
async def get_latest_image(camera_name: str, request: Request, response: Response):
    await ensure_camera_exists(camera_name)
    data = await get_camera_current(camera_name, request)

    etag = generate_etag(data)
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "no-cache, must-revalidate"

    return data

@router.get("/api/camera/{camera_name}/timelapse", response_model=CameraTimelapseResponse)
async def get_timelapse(camera_name: str, request: Request, response: Response):
    await ensure_camera_exists(camera_name)
    data = await get_camera_timelapse(camera_name, request)

    etag = generate_etag(data)
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "no-cache, must-revalidate"

    return data

# Agents ----------------------------------------------------
@router.get("/api/agents")
async def get_capture_agent_details(request: Request, response: Response):
    try:
        agents = await fetch_agents()

        payload = [c.model_dump() for c in agents]

        etag = generate_etag(payload)
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = "no-cache, must-revalidate"

        last_check = await redis_client.get("ca:last_refresh") or "never"
        return {
            "status": "success",
            "agents": payload,
            "total": len(payload),
            "last_refresh": last_check,
            "version": etag
        }

    except Exception as e:
        logger.exception("Failed to get capture agents")
        raise HTTPException(status_code=500, detail=str(e))

# Activity --------------------------------------------------
@router.get("/activity")
async def get_cameras_activity(request: Request):
    """Return counts and lists of online/offline cameras based on `last_capture_completed`."""

    try:
        online: List[str] = []
        offline: List[str] = []
        timestamps: Dict[str, str | None] = {}

        cameras = await fetch_cameras(request, full=False)
        for cam in cameras:
            # Separate into online/offline
            if cam.state == "online":
                online.append(cam.name)
            else:
                offline.append(cam.name)

            timestamps[cam.name] = cam.last_capture_completed

        return {
            "threshold_seconds": settings.STATUS_INTERVAL,
            "online_count": len(online),
            "offline_count": len(offline),
            "online": online,
            "offline": offline,
            "last_capture_completed": timestamps
        }
    except Exception as e:
        logger.exception("Failed to get camera activities")
        raise HTTPException(status_code=500, detail=str(e))
