#!/usr/bin/env python3

"""Fetch cameras from Opencast and store them in the Database"""

import asyncio
import time
import sys
import traceback

from opencast.opencast import CaptureAgent

from utils.settings import FetchSettings
from utils.database import create_db

from utils.camera import CameraRepository
from utils.schemas import CameraCreate

async def run(settings):
    engine, AsyncSessionLocal = create_db(settings)

    async with AsyncSessionLocal() as db:
        repo = CameraRepository(db)
        cameras_to_upsert = []

        # cameras = await repo.get_all()
        # print(cameras)

        response = settings.OC.get_capture_agent_capabilities().json()

        if "agents" not in response:
            print("No Capture Agents in response")
            return

        for data in response['agents']['agent']:
            ca = CaptureAgent(data)
            url = ca.get_capability('capture.device.presenter.src')
            print(f"{ca.name} {ca.state} {url}")

            if url and 'rtsp' in url:
                cameras_to_upsert.append( CameraCreate(name=ca.name, url=url, enabled=True) )

        # Bulk upsert all cameras at once
        if cameras_to_upsert:
            try:
                cameras = await repo.upsert_many(cameras_to_upsert)
                print(f"Successfully upserted {len(cameras)} cameras")
                await db.commit()
            except Exception as e:
                print(f"Error upserting cameras: {e}")
                await db.rollback()
                raise
        else:
            print("No cameras to upsert")

    # Clean shutdown
    await engine.dispose()

def main(settings):

    # print(settings.DATABASE_URL)

    start = time.time()

    try:
        asyncio.run(run(settings))
        # pass

    except KeyboardInterrupt:
        sys.exit(0)

    except Exception as e:
        print(f'ERR: {e}')
        traceback.print_exc()

    finally:
        print(f'Processing: {time.strftime("%H:%M:%S", time.gmtime(time.time() - start))}')

if __name__ == '__main__':
    settings = FetchSettings(SERVER_TYPE='script')
    settings.TITLE = "Camera Dashboard Script"
    main(settings)
