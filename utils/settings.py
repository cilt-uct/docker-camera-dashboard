import os
import re
import sys
import logging

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

from opencast.opencast import Opencast

# Default cameras (small example). Real cameras are loaded from an external file or Redis if provided.
DEFAULT_CAMERAS = [
    {"name": "example", "rtsp_url": "rtsp://example.local/cam01/axis-media/media.amp"}
]

logging.basicConfig(stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s %(process)d %(levelname)-8s %(filename)s(%(lineno)d) %(message)s')

logger = logging.getLogger()

# This line references a path for secret loading, but does not embed a secret.
class FetchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='/run/secrets/passwords',
                                        env_file_encoding='utf-8',
                                        frozen=False,
                                        extra='ignore')

    # Store the env_file path manually
    _env_file_used: Optional[str] = None

    ROOT_PATH: str = Field(default='/cams', validation_alias='ROOT_PATH')

    TITLE: str = Field(default='Camera Dashboard Service', description='The title of the service.')
    VERSION: str = Field(default='0.0.1')

    SERVER_TYPE: str = Field(default='dev', validation_alias='ENV', description='The environment type (e.g., dev, prod).')
    SERVER_DEBUG: bool = Field(default=False, validation_alias='DEBUG', description='Is the system running in debug mode.')
    SERVER_IN_DOCKER: bool = Field(default=False, validation_alias='RUNNING_IN_DOCKER', description='Is the system running in docker.')

    REDIS_HOST: str = Field(default='localhost', validation_alias='REDIS_HOST', description='Redis host.')
    REDIS_PASSWORD: str = Field(default='', validation_alias='REDIS_PASSWORD', description='Redis password.')
    REDIS_PORT: int = Field(default=6379, validation_alias='REDIS_PORT', description='Redis port.')

    OC_HOST: str = Field(default='localhost', validation_alias='OC_SERVER', description='Opencast server URL.')
    OC_USER: str = Field(default='brightspace', validation_alias='OC_USER', description='Opencast username.')
    OC_PASS: str = Field(default='brightspace', validation_alias='OC_PASS', description='Opencast password.')
    # Helpdesk contact
    CONTACT_EMAIL: str = Field(default='helpdesk@example.com', validation_alias='CONTACT_EMAIL', description='Helpdesk contact email.')

    CAMERAS_FILE: str = Field(default='/run/secrets/cameras', description='Path to a JSON file containing camera definitions.')
    IMAGE_DIR: str = Field(default='/shared_volume/images', description='Path to images folder that will contain a folder for each camera.')
    TIMELAPSE_DIR: str = Field(default='/shared_volume/timelapse', description='Path to timelapse folder that will contain a timelapse for each camera.')

    CAPTURE_INTERVAL: int = Field(default=300, description='Interval in seconds to capture camera images (5 minutes in seconds).')
    TIMELAPSE_INTERVAL: int = Field(default=900, description='Interval in seconds to run the timelapse generation (15 minutes in seconds).')
    CLEAN_INTERVAL: int = Field(default=604800, description='Interval in seconds for older files to be removed (7 * 24 * 60 * 60 = 7 days in seconds).')

    # Adjust these for your environment
    BATCH_SIZE: int = Field(default=5, description='Number of cameras to run concurrently')
    BATCH_DELAY: int = Field(default=10, description='Seconds between batches')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Save env_file if passed explicitly
        self._env_file_used = kwargs.get('_env_file', '/run/secrets/passwords')

    @property
    def OC(self) -> Opencast:
        """Create a Opencast client instance."""
        return Opencast(
            server=self.OC_HOST,
            username=self.OC_USER,
            password=self.OC_PASS,
        )

    @field_validator("SERVER_DEBUG", "SERVER_IN_DOCKER", mode="before")
    @classmethod
    def validate_bool(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "1", "yes"):
            return True
        if isinstance(value, str) and value.lower() in ("false", "0", "no"):
            return False
        return False

# -----------------------
# Camera loading helpers
# -----------------------
import json
try:
    import redis as _redis
except Exception:
    _redis = None


def load_cameras_from_file(path: str):
    """Load cameras from a JSON file at `path`. Returns list or None on failure."""
    try:
        if not path:
            return None
        if not Path(path).exists():
            return None
        with open(path, 'r') as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.debug(f"Could not load cameras from file {path}: {e}")
    return None


def load_cameras_from_redis(settings: 'FetchSettings'):
    """Load cameras from Redis key specified in settings. Returns list or None."""
    if _redis is None:
        logger.debug("redis library not available; skipping Redis camera load")
        return None
    try:
        rc = _redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD, decode_responses=True)
        val = rc.get(settings.CAMERAS_REDIS_KEY)
        if val:
            data = json.loads(val)
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.debug(f"Could not load cameras from redis: {e}")
    return None


def save_cameras_to_redis(settings: 'FetchSettings', cameras: list) -> bool:
    """Save a camera list to Redis. Returns True on success."""
    if _redis is None:
        logger.debug("redis library not available; cannot save cameras to redis")
        return False
    try:
        rc = _redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD, decode_responses=True)
        rc.set(settings.CAMERAS_REDIS_KEY, json.dumps(cameras))
        return True
    except Exception as e:
        logger.error(f"Failed to save cameras to redis: {e}")
        return False

# Initialize the cameras variable: prefer file (CAMERAS_FILE), then redis, else fallback to DEFAULT_CAMERAS
try:
    _settings_for_cameras = FetchSettings()
    print(f"Loading cameras using settings from env_file: {_settings_for_cameras.CAMERAS_FILE}")
    _cameras_from_file = load_cameras_from_file(_settings_for_cameras.CAMERAS_FILE)
    print(f"Loaded cameras from file: {_cameras_from_file is not None}")
    if _cameras_from_file:
        cameras = _cameras_from_file
    else:
        _cameras_from_redis = load_cameras_from_redis(_settings_for_cameras)
        cameras = _cameras_from_redis if _cameras_from_redis else DEFAULT_CAMERAS
except Exception:
    cameras = DEFAULT_CAMERAS


def refresh_cameras() -> list:
    """Refresh the module-level `cameras` variable by reading the file or Redis.

    Returns the refreshed camera list."""
    global cameras
    s = FetchSettings()
    from_file = load_cameras_from_file(s.CAMERAS_FILE)
    cainfo = get_opencast_cainfo()
    if from_file:
        cameras = from_file
        return cameras
    from_redis = load_cameras_from_redis(s)
    if from_redis:
        cameras = from_redis
        return cameras
    cameras = DEFAULT_CAMERAS
    return cameras

