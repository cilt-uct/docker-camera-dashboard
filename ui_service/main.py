from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates

# Configuration
from utils.settings import logger
from core import settings, redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- STARTUP ----
    start_time = datetime.now().astimezone().isoformat()

    try:
        await redis_client.set("ui_service_start", start_time)
        logger.info(f"UI started at {start_time}")
    except Exception as e:
        logger.warning(f"Failed to write startup time to Redis: {e}")

    yield

    # ---- SHUTDOWN ----
    logger.info("Shutting down UI service")

app = FastAPI(lifespan=lifespan)

# Mount shared volume for images and timelapses and assets
app.mount("/static", StaticFiles(directory="/shared_volume"), name="static")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# Setup Jinja Template folders
env = Environment(loader=FileSystemLoader("templates"))
templates = Jinja2Templates(directory="templates")

# Root ------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def get_home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

# API -------------------------------------------------------
from api import router as api_router
app.include_router(api_router)

# Status ----------------------------------------------------
@app.get("/status")
async def get_status(request: Request):
    schedule_service_start = await redis_client.get("scheduler_service_start")
    ui_service_start = await redis_client.get("ui_service_start")
    return {
        "service": settings.TITLE,
        "version": settings.VERSION,
        "environment": settings.SERVER_TYPE,
        "debug": settings.SERVER_DEBUG,
        "running_in_docker": settings.SERVER_IN_DOCKER,
        "scheduler_service_start" : schedule_service_start,
        "ui_service_start": ui_service_start,
        "activity": str(request.url_for('get_cameras_activity'))
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level='debug' if settings.SERVER_DEBUG else 'info',
        root_path=settings.ROOT_PATH
    )
