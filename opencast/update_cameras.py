#!/usr/bin/env python3
"""Fetch cameras from Opencast and store them into Redis using settings.save_cameras_to_redis"""
import json

from utils.settings import FetchSettings, save_cameras_to_redis


def main():
    settings = FetchSettings()
    try:
        response = settings.OC.get_cameras()

        cameras_data = response.json()

        # If opencast returns an object with 'agents' or similar, try to unwrap common shapes
        # If cameras_data is a dict with a single list under a key, try common keys
        if isinstance(cameras_data, dict):
            for k in ("agents", "cameras", "items", "results"):
                if k in cameras_data and isinstance(cameras_data[k], list):
                    cameras_data = cameras_data[k]
                    break

        # Save whatever we have to Redis
        ok = save_cameras_to_redis(settings, cameras_data)
        if ok:
            print(f"Saved cameras to redis key '{settings.CAMERAS_REDIS_KEY}'. Count: {len(cameras_data) if isinstance(cameras_data, list) else 'unknown'}")
        else:
            print("Failed to save cameras to redis; see logs for details.")

    except Exception as e:
        print("Error fetching cameras from Opencast:", e)
        raise


if __name__ == '__main__':
    main()
