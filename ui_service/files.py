import asyncio

from pathlib import Path
from fastapi import Request

from utils.settings import logger
from core import settings

# Internal (SYNC) -------------------------------------------
def _get_latest_image_path(image_dir: Path):
    if not image_dir.exists():
        return None

    files = list(image_dir.iterdir())
    if not files:
        return None

    return max(files)

def _path_exists(path: Path):
    return path.exists()

def _list_images(img_dir: Path):
    if not img_dir.exists():
        return []

    return sorted(img_dir.glob("*.jpg"))

# Public (ASYNC) --------------------------------------------
async def get_image_url(camera_name: str, request: Request) -> str | None:
    image_dir = Path(settings.IMAGE_DIR) / f"camera_{camera_name}"

    latest_image = await asyncio.to_thread(_get_latest_image_path, image_dir)

    if not latest_image:
        logger.warning(f"{camera_name} No images found")
        return None

    return str(request.url_for("static", path=f"images/camera_{camera_name}/{latest_image.name}"))

async def get_timelapse_url(camera_name: str, type: str, request: Request) -> str | None:
    path = Path(settings.TIMELAPSE_DIR) / f"camera_{camera_name}.{type}"
    exists = await asyncio.to_thread(_path_exists, path)

    if not exists:
        logger.warning(f"{camera_name} Timelapse not found")
        return None

    return str(request.url_for("static", path=f"timelapse/camera_{camera_name}.{type}"))

async def get_thumbnail(camera_name: str, type: str, request: Request) -> str | None:
    thumbfile = Path(f"/shared_volume/{type}/{camera_name}_thumb.jpg")

    exists = await asyncio.to_thread(_path_exists, thumbfile)

    if not exists:
        logger.warning(f"{camera_name} Thumbnail not found")
        return None

    return str(request.url_for("static", path=f"{type}/{camera_name}_thumb.jpg"))

async def get_logfile(camera_name: str, type: str, request: Request) -> str | None:
    logfile = Path(f"/shared_volume/{type}/{camera_name}.log")

    exists = await asyncio.to_thread(_path_exists, logfile)

    if not exists:
        logger.warning(f"{camera_name} log file not found")
        return None

    return str(request.url_for("static", path=f"{type}/{camera_name}.log"))

async def get_camera_images(camera_name: str, request: Request):
    img_dir = Path(settings.IMAGE_DIR) / f"camera_{camera_name}"
    if not img_dir.exists():
        return []

    images = await asyncio.to_thread(_list_images, img_dir)

    return [
        str(request.url_for("static", path=f"images/camera_{camera_name}/{img.name}"))
        for img in images
    ]
