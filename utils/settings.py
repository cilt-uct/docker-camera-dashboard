import os
import sys
import logging

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

from urllib.parse import quote_plus

from opencast.opencast import Opencast
from utils.simple import SimpleHTML

logging.basicConfig(stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s %(process)d %(levelname)-8s %(filename)s(%(lineno)d) %(message)s')

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger()

DEFAULT_ENV_FILES = [
    "/run/secrets/passwords",
    "/usr/local/serverconfig/camera_dashboard.cfg",
    ".env"
]

env_file = next((f for f in DEFAULT_ENV_FILES if os.path.exists(f)), None)

# This line references a path for secret loading, but does not embed a secret.
class FetchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=env_file,
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

    MYSQL_HOST: str = Field(default='server', validation_alias='MYSQL_HOST', description='MySQL host.')
    MYSQL_DB: str = Field(default='database', validation_alias='MYSQL_DB', description='MySQL Database.')
    MYSQL_USER: str = Field(default='user', validation_alias='MYSQL_USER', description='MySQL username.')
    MYSQL_PASSWORD: str = Field(default='password', validation_alias='MYSQL_PASSWORD', description='MySQL password.')
    MYSQL_PORT: int = Field(default=3306, validation_alias='MYSQL_PORT', description='MySQL port.')

    REDIS_HOST: str = Field(default='localhost', validation_alias='REDIS_HOST', description='Redis host.')
    REDIS_PASSWORD: str = Field(default='', validation_alias='REDIS_PASSWORD', description='Redis password.')
    REDIS_PORT: int = Field(default=6379, validation_alias='REDIS_PORT', description='Redis port.')
    REDIS_CLEAN_START: bool = Field(default=False, validation_alias='REDIS_CLEAN_START', description='Whether to clear Redis on startup.')

    OC_HOST: str = Field(default='localhost', validation_alias='OC_SERVER', description='Opencast server URL.')
    OC_USER: str = Field(default='opencast', validation_alias='OC_USER', description='Opencast username.')
    OC_PASS: str = Field(default='password', validation_alias='OC_PASS', description='Opencast password.')

    PYCA_PAGE_URL: str = Field(default='', validation_alias='PYCA_PAGE_URL', description='The URL of the PyCA overview page.')

    # Helpdesk contact
    CONTACT_EMAIL: str = Field(default='helpdesk@example.com', validation_alias='CONTACT_EMAIL', description='Helpdesk contact email.')

    IMAGE_DIR: str = Field(default='/shared_volume/images', description='Path to images folder that will contain a folder for each camera.')
    TIMELAPSE_DIR: str = Field(default='/shared_volume/timelapse', description='Path to timelapse folder that will contain a timelapse for each camera.')

    CAPTURE_INTERVAL: int = Field(default=300, description='Interval in seconds to capture camera images (5 minutes in seconds).')
    STATUS_INTERVAL: int = Field(default=1200, description='Interval in seconds to mark camera as offline (15 minutes in seconds).')
    TIMELAPSE_INTERVAL: int = Field(default=900, description='Interval in seconds to run the timelapse generation (15 minutes in seconds).')
    CLEAN_INTERVAL: int = Field(default=604800, description='Interval in seconds for older files to be removed (7 * 24 * 60 * 60 = 7 days in seconds).')

    # Fetch event page size
    SCHEDULE_PAGE_SIZE: int = Field(default=200, description='Number of events to fetch per page from the schedule.')

    # Adjust these for your environment
    BATCH_SIZE: int = Field(default=10, description='Number of cameras to run concurrently')
    BATCH_DELAY: int = Field(default=10, description='Seconds between batches')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Save env_file if passed explicitly
        self._env_file_used = kwargs.get('_env_file')
        logger.debug(f"Using env file: {env_file}")

        self.SERVER_TYPE = kwargs.get('SERVER_TYPE', self.SERVER_TYPE)

        # if we are running as script then we don't need the rest of the initialization to happen
        if 'script' in self.SERVER_TYPE:
            return

        # explicitly set self.Redis_password, was returning the file path name
        password_file = "/run/secrets/redis_password"

        if os.path.exists(password_file):
            try:
                with open(password_file, "r") as f:
                    self.REDIS_PASSWORD = f.read().strip()

                logger.debug(f"Redis password loaded from secret file (length: {len(self.REDIS_PASSWORD)})")
            except Exception as e:
                logger.error(f"Failed to read Redis password file: {e}")
                self.REDIS_PASSWORD = ""
        else:
            logger.warning("Redis password file not found at /run/secrets/redis_password — connecting without password")
            self.REDIS_PASSWORD = ""

    @property
    def OC(self) -> Opencast:
        """Create a Opencast client instance."""
        return Opencast(
            server=self.OC_HOST,
            username=self.OC_USER,
            password=self.OC_PASS,
        )

    def HTML(self, username:str | None = None, password:str | None = None) -> SimpleHTML:
        """Create a SimpleHTML client instance."""
        return SimpleHTML(
            username=username,
            password=password,
        )

    @property
    def DATABASE_URL(self) -> str:
        # Encode the password to handle special characters
        encoded_password = quote_plus(self.MYSQL_PASSWORD)
        encoded_user = quote_plus(self.MYSQL_USER)

        return f"mysql+asyncmy://{encoded_user}:{encoded_password}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"

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
