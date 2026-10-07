import asyncio
import json
import os
import socket
import time
import redis.asyncio as redis

from urllib.parse import urlparse
from dateutil.parser import parse as parse_dt
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from subprocess import call

from pathlib import Path

from utils.settings import FetchSettings, logger
from utils.database import create_db
from utils.camera import CameraRepository
from utils.schemas import CameraCreate, CameraUpdate

from opencast.opencast import CaptureAgent

settings = FetchSettings()
settings.TITLE = "Fetch Camera Images Service"

# Utility Functions
# -----------------------------------------------
def replace_rtspt(url: str) -> str:
    if not url:
        return url
    return url.replace("rtspt://", "rtsp://")

def str_to_dt_or_none(s: str):
    if not s:
        return None
    try:
        return parse_dt(s)
    except Exception:
        # if parsing of datetime fails, return None
        return None

def get_redis(settings):
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD, #This line references a path for secret loading, but does not embed a secret.
        decode_responses=True
    )

async def fetch_cameras_from_redis(rc) -> list[dict]:
    """Get all camera details from Redis as a list of dicts."""
    camera_names = await rc.smembers("camera:index")
    cameras = []

    for name in camera_names:
        cam_hash = await rc.hgetall(f"camera:{name}")
        if cam_hash:
            cameras.append({
                "name": cam_hash.get("name"),
                "url": cam_hash.get("url"),
                "enabled": cam_hash.get("enabled") == "True"
            })
    return cameras

async def mark_camera_dirty(rc, camera_name: str):
    """
    Add the camera to the 'camera:dirty' set in Redis
    so it can be processed later for DB updates.
    """
    try:
        await rc.sadd("camera:dirty", camera_name)
        logger.debug(f"Marked camera {camera_name} as dirty")
    except Exception as e:
        logger.warning(f"Failed to mark camera {camera_name} as dirty: {e}")

def normalize_agent_status(status: str) -> str:
    if not status:
        return "unknown"
    return status.split(".")[-1].lower()

def format_datetime_for_redis(dt_value):
    """Convert datetime to string format suitable for Redis storage"""
    if dt_value is None:
        return None

    if isinstance(dt_value, datetime):
        # Make it timezone-aware if it isn't already
        if dt_value.tzinfo is None:
            # Use the system's local timezone
            dt_value = dt_value.astimezone()

        return dt_value.isoformat(timespec='seconds')

    if isinstance(dt_value, str):
        # Handle UTC format with Z
        if dt_value.endswith('Z'):
            try:
                utc_time = datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
                local_time = utc_time.astimezone()
                return local_time.isoformat(timespec='seconds')
            except ValueError:
                pass
        return dt_value

    return str(dt_value)

# Capture & Timelapse
# -----------------------------------------------

async def is_camera_alive(rtsp_url, timeout=2):
    """
    Quickly check if an RTSP camera is reachable by trying to open a TCP connection
    on the RTSP port (default 554).
    """
    parsed = urlparse(rtsp_url)
    host = parsed.hostname
    port = parsed.port or 554

    loop = asyncio.get_running_loop()
    try:
        fut = loop.run_in_executor(
            None,
            lambda: socket.create_connection((host, port), timeout)
        )
        conn = await asyncio.wait_for(fut, timeout=timeout)
        conn.close()
        return True
    except Exception:
        # well some timeout or connection error occurred, so we assume the camera is not alive
        return False

async def _capture_one(loop, ca, settings, semaphore, rc):
    """
    Capture a single camera image with concurrency control.
    """
    async with semaphore:

        # Record when a capture was attempted
        iso_ts = datetime.now().astimezone().isoformat(timespec='seconds')
        try:
            await rc.hset(f"camera:{ca['name']}", "last_capture_attempt", iso_ts)
            await mark_camera_dirty(rc, ca['name'])

            logger.debug(f"Set last_capture_attempt for camera:{ca['name']}={iso_ts}")
        except Exception as e:
            logger.warning(f"Failed to set last_capture_attempt for {ca['name']}: {e}")

        if not await is_camera_alive(ca["url"]):
            logger.warning(f"[SKIP] Camera {ca['name']} not reachable")
            return

        timestamp = int(time.time())
        output_image = Path(settings.IMAGE_DIR) / f"camera_{ca['name']}" / f"{timestamp}.jpg"
        thumb_image = Path(settings.IMAGE_DIR) / f"{ca['name']}_thumb.jpg"
        logfile = Path(settings.IMAGE_DIR) / f"{ca['name']}.log"

        output_image.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"[CAPTURE] Camera {ca['name']} -> {output_image}")
        ret = await loop.run_in_executor(
            None,
            call,
            ["./scripts/capture_images.sh", ca['url'],
                                            ca['name'],
                                            str(output_image),
                                            str(thumb_image),
                                            str(logfile)]
        )

        # If the capture command succeeded, record completion timestamp
        if ret == 0:
            iso_ts = datetime.now().astimezone().isoformat(timespec='seconds')
            try:
                await rc.hset(f"camera:{ca['name']}", "last_capture_completed", iso_ts)
                await mark_camera_dirty(rc, ca['name'])

                logger.debug(f"Set last_capture_completed for camera:{ca['name']}={iso_ts}")
            except Exception as e:
                logger.warning(f"Failed to set last_capture_completed for {ca['name']}: {e}")
        else:
            logger.warning(f"[CAPTURE] script returned {ret} for {ca['name']}")

async def capture_images(settings):
    """
    Capture images from all cameras in batches with staggered delay
    and semaphore-limited concurrency.
    Uses a per-run async Redis client so tasks don't share a client bound to a different loop.
    """

    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(settings.BATCH_SIZE)

    # Create an async Redis client for this run
    rc = get_redis(settings)

    try:
        all_cameras = await fetch_cameras_from_redis(rc)
        for i in range(0, len(all_cameras), settings.BATCH_SIZE):
            batch = all_cameras[i:i + settings.BATCH_SIZE]
            tasks = [
                asyncio.create_task(_capture_one(loop, ca, settings, semaphore, rc))
                for ca in batch
            ]

            await asyncio.gather(*tasks)

            # Delay before starting the next batch
            if i + settings.BATCH_SIZE < len(all_cameras):
                logger.info(f"Waiting {settings.BATCH_DELAY}s before next batch...")
                await asyncio.sleep(settings.BATCH_DELAY)

        logger.info("All cameras processed")
    finally:
        # Close/disconnect the per-run Redis client
        try:
            close_coro = rc.aclose()
            if close_coro and asyncio.iscoroutine(close_coro):
                await close_coro
        except Exception:
            try:
                await rc.connection_pool.disconnect()
            except Exception:
                # if pool does not disconnect, just pass
                pass

async def _generate_timelapse(loop, ca, settings, semaphore, rc):
    """
    Generate a WebM+MP4 for one camera with concurrency control.
    `rc` is the per-run async Redis client passed from the caller.
    """
    async with semaphore:
        image_dir = Path(settings.IMAGE_DIR) / f"camera_{ca['name']}"
        output_base = Path(settings.TIMELAPSE_DIR) / f"camera_{ca['name']}"
        logfile = Path(settings.TIMELAPSE_DIR) / f"{ca['name']}.log"

        output_base.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"[Timelapse] Generating WebM+MP4 for {ca['name']}")
        ret = await loop.run_in_executor(
            None,
            call,
            ["./scripts/generate_timelapse.sh", str(image_dir), ca['name'], str(output_base), str(logfile)]
        )

        # If the capture command succeeded, record completion timestamp
        if ret == 0:
            iso_ts = datetime.now().astimezone().isoformat(timespec='seconds')
            try:
                await rc.hset(f"camera:{ca['name']}", "last_timelapse_run", iso_ts)
                await mark_camera_dirty(rc, ca['name'])

                logger.debug(f"Set last_timelapse_run for camera:{ca['name']}={iso_ts}")
            except Exception as e:
                logger.warning(f"Failed to set last_timelapse_run for {ca['name']}: {e}")
        else:
            logger.warning(f"[Timelapse] script returned {ret} for {ca['name']}")

async def generate_timelapses(settings):
    """
    Generate timelapses for all cameras in batches with staggered delay
    and semaphore-limited concurrency.
    Uses a per-run async Redis client to avoid attaching futures to a different loop.
    """
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(settings.BATCH_SIZE)

    # Create an async Redis client for this run
    rc = get_redis(settings)

    try:
        # Process cameras in batches
        all_cameras = await fetch_cameras_from_redis(rc)
        for i in range(0, len(all_cameras), settings.BATCH_SIZE):
            batch = all_cameras[i:i + settings.BATCH_SIZE]
            tasks = [
                asyncio.create_task(_generate_timelapse(loop, ca, settings, semaphore, rc))
                for ca in batch
            ]

            await asyncio.gather(*tasks)

            # Delay before next batch
            if i + settings.BATCH_SIZE < len(all_cameras):
                logger.info(f"Waiting {settings.BATCH_DELAY}s before next timelapse batch...")
                await asyncio.sleep(settings.BATCH_DELAY)

        logger.info("All timelapses generated")
    finally:
        try:
            close_coro = rc.aclose()
            if close_coro and asyncio.iscoroutine(close_coro):
                await close_coro
        except Exception:
            try:
                await rc.connection_pool.disconnect()
            except Exception:
                # if pool does not disconnect, just pass
                pass

# Opencast
# -----------------------------------------------
async def update_capture_agent_details(settings):
    """
    Load Opencast Capture Agents into Redis, and create missing cameras in DB.
    """
    rc = get_redis(settings)
    engine, AsyncSessionLocal = create_db(settings)

    async with AsyncSessionLocal() as db:
        repo = CameraRepository(db)

        await rc.set("ca:last_refresh", datetime.now().astimezone().isoformat(timespec='seconds'))

        ca_names = settings.OC.get_ca_names().json()
        await rc.hset("ca:display", mapping=ca_names)

        response = settings.OC.get_capture_agent_capabilities().json()
        if "agents" not in response:
            logger.error("No Capture Agents in response")
            return

        for data in response['agents']['agent']:
            ca = CaptureAgent(data)

            # ca:index -> set of capture agent names
            await rc.sadd("ca:index", ca.name)

            # ca:{name} -> hash of capture agent details
            await rc.hset(f"ca:{ca.name}", mapping=ca.get_dict(display=ca_names.get(ca.name, '') if ca_names else ''))

            url = ca.get_capability('capture.device.presenter.src')

            if not url or 'rtsp' not in url:
                logger.warning(f"CA {ca.name} has no capture.device.presenter.src capability, skipping camera creation")
                continue

            # Check if camera exists in database
            camera_in_db = await repo.get_by_name(ca.name)
            camera_in_redis = await rc.hgetall(f"camera:{ca.name}")

            # Camera is in Database, but update the URL if it's different
            if camera_in_db:
                if camera_in_db.url != url:
                    await repo.update(camera_in_db.id, CameraUpdate(url=url))
                    await db.commit()
                    logger.info(f"Updated URL for camera {ca.name} in DB")

                if camera_in_redis and camera_in_redis.get("url") != url:
                    await rc.hset(f"camera:{ca.name}", "url", replace_rtspt(url))
                    await mark_camera_dirty(rc, ca.name)
                    logger.info(f"Updated URL for camera {ca.name} in Redis")

            else:
                # Add camera to Redis and to Database
                new_camera = await repo.create(CameraCreate(name=ca.name, url=url, enabled=True))
                await db.commit()

                # camera:index -> set of names
                await rc.sadd("camera:index", ca.name)

                # camera:{name} -> hash of camera details
                cam_dict = {
                    "id": str(new_camera.id),
                    "name": new_camera.name,
                    "url": replace_rtspt(new_camera.url),
                    "enabled": str(new_camera.enabled),
                    "last_capture_completed": str(new_camera.last_capture_completed) if new_camera.last_capture_completed else "",
                    "last_capture_attempt": str(new_camera.last_capture_attempt) if new_camera.last_capture_attempt else "",
                    "last_timelapse_run": str(new_camera.last_timelapse_run) if new_camera.last_timelapse_run else "",
                    "updated_at": str(new_camera.updated_at) if new_camera.updated_at else "",
                }

                await rc.hset(f"camera:{new_camera.name}", mapping=cam_dict)
                logger.info(f"Created new camera from capture agent: {ca.name}")

        logger.info(f"Updated details for {len(response['agents']['agent'])} CA's")

    await engine.dispose()

async def update_capture_agent_state(settings):
    """
    Get the capture agents current state and update that details
    """
    rc = get_redis(settings)
    await rc.set("ca:last_refresh", datetime.now().astimezone().isoformat(timespec='seconds'))

    response = settings.OC.get_capture_agent_status().json()
    if "results" not in response:
        logger.error("No Capture Agents in response")
        return

    async with rc.pipeline() as pipe:
        for ca in response['results']:
            update_value = ca.get('Update')
            if update_value is None:
                update_value = datetime.now().astimezone()

            pipe.hset(f"ca:{ca['Name']}", mapping={
                "state": normalize_agent_status(ca['Status']),
                "last_updated": format_datetime_for_redis(update_value)
            })
        await pipe.execute()

    logger.info(f"Updated states for {len(response['results'])} CA's")

SCHEDULE_PAGE_SIZE = 100

def map_external_event(ev: dict) -> dict:
    """Map an External API event to the schedule event shape used by the UI."""
    scheduling = ev.get('scheduling') or {}
    start = ev.get('start')

    end = None
    start_dt = str_to_dt_or_none(start)
    if start_dt is not None and ev.get('duration') not in (None, ''):
        try:
            end_dt = start_dt + timedelta(milliseconds=int(ev['duration']))
            end = end_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        except (TypeError, ValueError):
            end = None

    return {
        'id': ev.get('identifier'),
        'title': ev.get('title'),
        'start_date': start,
        'end_date': end or scheduling.get('end'),
        'technical_start': scheduling.get('start') or start,
        'technical_end': scheduling.get('end') or end,
        'event_status': ev.get('status'),
        'displayable_status': ev.get('status'),
        'location': ev.get('location'),
        'agent_id': scheduling.get('agent_id') or ev.get('location'),
    }

async def update_schedule(settings):
    """
    Fetch today's events from Opencast, enrich them with camera and capture agent
    details from Redis, and store the grouped schedule in Redis as 'schedule:today'.
    """
    rc = get_redis(settings)
    try:
        now = datetime.now().astimezone()
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1) - timedelta(seconds=1)
        utc_fmt = '%Y-%m-%dT%H:%M:%SZ'

        oc = settings.OC
        events = []
        offset = 0
        while True:
            results = oc.get_events(start_date=start_local.astimezone(timezone.utc).strftime(utc_fmt),
                                    end_date=end_local.astimezone(timezone.utc).strftime(utc_fmt),
                                    sort='location:ASC',
                                    withPublications=False,
                                    withScheduling=True,
                                    offset=offset, limit=SCHEDULE_PAGE_SIZE)
            if results is None:
                logger.error("Failed to fetch schedule from Opencast")
                return

            events.extend(map_external_event(ev) for ev in results)
            offset += len(results)

            if len(results) < SCHEDULE_PAGE_SIZE:
                break

        display_names = await rc.hgetall("ca:display")
        locations = {}
        for ev in events:
            name = ev.get('agent_id') or ev.get('location') or 'unknown'

            if name not in locations:
                ca_hash = await rc.hgetall(f"ca:{name}")
                cam_hash = await rc.hgetall(f"camera:{name}")
                locations[name] = {
                    "name": name,
                    "display": ca_hash.get("display") or display_names.get(name) or name,
                    "agent_state": ca_hash.get("state") or "unknown",
                    "agent_last_updated": ca_hash.get("last_updated") or None,
                    "has_camera": bool(cam_hash),
                    "camera_enabled": cam_hash.get("enabled") == "True",
                    "camera_last_capture_completed": cam_hash.get("last_capture_completed") or None,
                    "events": []
                }

            locations[name]["events"].append(ev)

        for loc in locations.values():
            loc["events"].sort(key=lambda e: e.get("start_date") or "")

        payload = {
            "date": start_local.date().isoformat(),
            "window_start": start_local.isoformat(timespec='seconds'),
            "window_end": end_local.isoformat(timespec='seconds'),
            "last_refresh": datetime.now().astimezone().isoformat(timespec='seconds'),
            "total": len(events),
            "locations": sorted(locations.values(), key=lambda loc: loc["name"].lower())
        }

        await rc.set("schedule:today", json.dumps(payload))
        logger.info(f"Updated schedule: {len(events)} events in {len(locations)} locations")

    except Exception as e:
        logger.exception(f"Failed to update schedule: {e}")
    finally:
        try:
            await rc.aclose()
        except Exception:
            # closing the client should never crash the job
            pass

async def update_capture_agent_state_and_schedule(settings):
    await update_capture_agent_state(settings)
    await update_schedule(settings)


# Cleanup
# -----------------------------------------------

def clean_images(settings):
    """
    Deletes files older than 7 days from the specified folder and subfolders.
    """
    cutoff_time = time.time() - settings.CLEAN_INTERVAL

    for root, dirs, files in os.walk(settings.IMAGE_DIR, topdown=False):  # Traverse bottom-up to clean folders
        for filename in files:
            file_path = os.path.join(root, filename)
            if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff_time:
                try:
                    os.remove(file_path)
                    logger.debug(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting {file_path}: {e}")

        # Optionally remove empty directories after deleting files
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            if not os.listdir(dir_path):  # Check if folder is empty
                try:
                    os.rmdir(dir_path)
                    logger.debug(f"Deleted empty folder: {dir_path}")
                except Exception as e:
                    logger.error(f"Error deleting folder {dir_path}: {e}")

async def flush_dirty_cameras_to_db(settings):
    """
    Take all dirty cameras from Redis and update the DB model.
    """
    rc = get_redis(settings)
    engine, AsyncSessionLocal = create_db(settings)

    async with AsyncSessionLocal() as db:
        repo = CameraRepository(db)
        dirty_cameras = await rc.smembers("camera:dirty")

        if not dirty_cameras:
            return

        processed = 0
        for cam_name in dirty_cameras:
            cam_hash = await rc.hgetall(f"camera:{cam_name}")
            if not cam_hash:
                continue

            # Get the camera DB object
            cam_obj = await repo.get_by_name(cam_name)
            if not cam_obj:
                continue

            # Convert Redis hash fields to the Pydantic CameraUpdate model
            update_data = CameraUpdate(
                url=cam_hash.get("url"),
                last_capture_attempt=str_to_dt_or_none(cam_hash.get("last_capture_attempt")),
                last_capture_completed=str_to_dt_or_none(cam_hash.get("last_capture_completed")),
                last_timelapse_run=str_to_dt_or_none(cam_hash.get("last_timelapse_run"))
            )

            # Update the DB
            await repo.update(cam_obj.id, update_data)

            # Remove this camera from the dirty set after processing
            await rc.srem("camera:dirty", cam_name)
            processed += 1

        await db.commit()
        print(f"Flushed {processed} dirty cameras to DB")

    await engine.dispose()

async def clear_redis_on_startup(settings):
    rc = get_redis(settings)

    # Clear the current database only
    await rc.flushdb()

    logger.info("Redis cleared on startup")

# Database -> Redis Sync Function
# -----------------------------------------------
async def load_cameras_to_redis(settings):
    """Fetch all cameras from DB and populate Redis on startup."""
    rc = get_redis(settings)
    engine, AsyncSessionLocal = create_db(settings)

    async with AsyncSessionLocal() as db:
        repo = CameraRepository(db)
        all_cameras = await repo.get_all()

        # Clear previous index
        await rc.delete("camera:index")

        for cam in all_cameras:
            # camera:index -> set of names
            await rc.sadd("camera:index", cam.name)

            # camera:{name} -> hash of camera details
            cam_dict = {
                "id": str(cam.id),
                "name": cam.name,
                "url": replace_rtspt(cam.url),
                "enabled": str(cam.enabled),
                "last_capture_completed": format_datetime_for_redis(cam.last_capture_completed) or "",
                "last_capture_attempt": format_datetime_for_redis(cam.last_capture_attempt) or "",
                "last_timelapse_run": format_datetime_for_redis(cam.last_timelapse_run) or "",
                "updated_at": format_datetime_for_redis(cam.updated_at) or "",
            }
            await rc.hset(f"camera:{cam.name}", mapping=cam_dict)

        logger.info(f"Loaded {len(all_cameras)} cameras into Redis")

    await engine.dispose()


# Scheduler entry
# --------------------------
def capture_images_sync():
    asyncio.run(capture_images(settings))

def generate_timelapses_sync():
    asyncio.run(generate_timelapses(settings))

def flush_dirty_sync():
    asyncio.run(flush_dirty_cameras_to_db(settings))

def update_capture_agent_details_sync():
    asyncio.run(update_capture_agent_details(settings))

def update_capture_agent_state_sync():
    asyncio.run(update_capture_agent_state_and_schedule(settings))

async def startup():
    if settings.REDIS_CLEAN_START:
        await clear_redis_on_startup(settings) # start fresh

    await load_cameras_to_redis(settings)
    await update_capture_agent_details(settings)
    await update_capture_agent_state(settings)
    await update_schedule(settings)
    logger.info("Startup load complete: cameras + capture agents synced to Redis.")

if __name__ == "__main__":
    asyncio.run(startup())

    scheduler = BackgroundScheduler()

    # Capture jobs for all cameras split into batches
    scheduler.add_job(capture_images_sync, 'interval', seconds=settings.CAPTURE_INTERVAL, max_instances=1)
    scheduler.add_job(generate_timelapses_sync, 'interval', seconds=settings.TIMELAPSE_INTERVAL, max_instances=1)

    # Opencast - Get Capture Agent Status
    scheduler.add_job(update_capture_agent_details_sync, 'interval', hours=1, next_run_time=datetime.now() + timedelta(seconds=30))
    scheduler.add_job(update_capture_agent_state_sync, 'interval', minutes=5, next_run_time=datetime.now() + timedelta(seconds=40))

    # Cleanup - remove old images and timelapses and write updates to DB
    scheduler.add_job(clean_images, 'interval', args=[settings], days=1, next_run_time=datetime.now() + timedelta(seconds=5))
    scheduler.add_job(flush_dirty_sync, 'interval', minutes=5, next_run_time=datetime.now() + timedelta(seconds=10))
    scheduler.start()

    rc = get_redis(settings)
    start_time = datetime.now().astimezone().isoformat(timespec='seconds')
    asyncio.run(rc.set('scheduler_service_start', start_time))
    logger.info(f"Scheduler started at {start_time}")

    try:
        while True:
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()
        asyncio.run(rc.close())
