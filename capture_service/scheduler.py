import asyncio
import os
import time
import socket
from urllib.parse import urlparse
import redis.asyncio as redis

from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from subprocess import call

from pathlib import Path

# Configuration
from utils.settings import FetchSettings, logger, cameras
settings = FetchSettings()
settings.TITLE = "Fetch Camera Images Service"

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True
)

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
        return False

async def _capture_one(loop, ca, settings, semaphore, rc):
    """
    Capture one camera image, skipping if the camera is offline.
    `rc` is an async Redis client created per run to avoid cross-loop attachment errors.
    """
    async with semaphore:

        # Record when a capture was attempted
        iso_ts = datetime.now().isoformat()
        try:
            await rc.set(f"camera:{ca['name']}:last_capture_attempt", iso_ts)
            logger.debug(f"Set redis key camera:{ca['name']}:last_capture_attempt={iso_ts}")
        except Exception as e:
            logger.warning(f"Failed to set last_capture_attempt for {ca['name']}: {e}")

        if not await is_camera_alive(ca["rtsp_url"]):
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
            ["./scripts/capture_images.sh", ca['rtsp_url'],
                                            ca['name'],
                                            str(output_image),
                                            str(thumb_image),
                                            str(logfile)]
        )

        # If the capture command succeeded, record completion timestamp
        if ret == 0:
            iso_ts = datetime.now().isoformat()
            try:
                await rc.set(f"camera:{ca['name']}:last_capture_completed", iso_ts)
                logger.debug(f"Set redis key camera:{ca['name']}:last_capture_completed={iso_ts}")
            except Exception as e:
                logger.warning(f"Failed to set last_capture_completed for {ca['name']}: {e}")
        else:
            logger.warning(f"[CAPTURE] capture script returned {ret} for {ca['name']}")

async def capture_images(settings):
    """
    Capture images from all cameras in batches with staggered delay
    and semaphore-limited concurrency.
    Uses a per-run async Redis client so tasks don't share a client bound to a different loop.
    """
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(settings.BATCH_SIZE)

    # Create an async Redis client for this run
    rc = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )

    try:
        # Process cameras in batches
        for i in range(0, len(cameras), settings.BATCH_SIZE):
            batch = cameras[i:i + settings.BATCH_SIZE]
            tasks = [
                asyncio.create_task(_capture_one(loop, ca, settings, semaphore, rc))
                for ca in batch
            ]

            await asyncio.gather(*tasks)

            # Delay before starting the next batch
            if i + settings.BATCH_SIZE < len(cameras):
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

        # Record when a timelapse generation was started
        iso_ts = datetime.now().isoformat()
        try:
            await rc.set(f"camera:{ca['name']}:last_timelapse_run", iso_ts)
            logger.debug(f"Set redis key camera:{ca['name']}:last_timelapse_run={iso_ts}")
        except Exception as e:
            logger.warning(f"Failed to set last_timelapse_run for {ca['name']}: {e}")

        logger.info(f"[Timelapse] Generating WebM+MP4 for {ca['name']}")
        await loop.run_in_executor(
            None,
            call,
            ["./scripts/generate_timelapse.sh", str(image_dir), ca['name'], str(output_base), str(logfile)]
        )

async def generate_timelapses(settings):
    """
    Generate timelapses for all cameras in batches with staggered delay
    and semaphore-limited concurrency.
    Uses a per-run async Redis client to avoid attaching futures to a different loop.
    """
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(settings.BATCH_SIZE)

    # Create an async Redis client for this run
    rc = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )

    try:
        # Process cameras in batches
        for i in range(0, len(cameras), settings.BATCH_SIZE):
            batch = cameras[i:i + settings.BATCH_SIZE]
            tasks = [
                asyncio.create_task(_generate_timelapse(loop, ca, settings, semaphore, rc))
                for ca in batch
            ]

            await asyncio.gather(*tasks)

            # Delay before next batch
            if i + settings.BATCH_SIZE < len(cameras):
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
                pass

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

if __name__ == "__main__":
    # Wrap async functions for scheduler
    def capture_images_sync():
        asyncio.run(capture_images(settings))

    def generate_timelapses_sync():
        asyncio.run(generate_timelapses(settings))

    scheduler = BackgroundScheduler()
    scheduler.add_job(capture_images_sync, 'interval', seconds=settings.CAPTURE_INTERVAL)
    scheduler.add_job(generate_timelapses_sync, 'interval', seconds=settings.TIMELAPSE_INTERVAL)
    scheduler.add_job(clean_images, 'interval', args=[settings], days=1, next_run_time=datetime.now() + timedelta(seconds=5))
    scheduler.start()

    start_time = datetime.now().isoformat()
    asyncio.run(redis_client.set('scheduler_service_start', start_time))
    logger.info(f"Scheduler started. { start_time}")
    logger.info(type(redis_client))

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()