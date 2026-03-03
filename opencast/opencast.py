import httpx
import logging
import time
from httpx import DigestAuth
from utils.rest import RestClient
from datetime import datetime, timedelta, timezone
from typing import Optional


attributes = [attr for attr in dir(RestClient) if not attr.startswith('__')]
print(attributes)

logger = logging.getLogger(__name__)

class Opencast(object):

    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        # connection_name:str,

        timeout: float = 10,
        retries: int = 3,
        backoff_factor: float = 0.3,
        headers: dict = None
        ) -> None:
        """Instantiates library.

        Args:
            server (str): The URL of the Opencast Server
            username (str): The username to use
            password (str): The password to use
        """
        self.server = server
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.headers = headers or {}

    @classmethod
    def get_classname(cls):
        return cls.__name__

    def create_digest_client(self):

        DEFAULT_DIGEST_HEADER = {
            'X-Requested-Auth': 'Digest',
            'User-Agent': f'{self.get_classname()}/{datetime.now().strftime("%Y-%m-%d")}'
        }

        headers = {**DEFAULT_DIGEST_HEADER, **self.headers}

        self.client = RestClient(
            base_url=self.server,
            auth=(self.username, self.password),
            auth_type='digest',
            timeout=self.timeout,
            retries=self.retries,
            backoff_factor=self.backoff_factor,
            headers=headers
        )

        # info = self.get_info()
        # if not info:
        #     raise Exception(f"Unexpected response from {self.server}/info/me.json")

        # logging.info(
        #     f"Authenticated to {self.server} as {info.get('user', {}).get('username')}"
        # )

        # if 'roles' in info and 'ROLE_API' not in info['roles']:
        #     raise Exception(
        #         f"Authenticated user {self.username} does not have ROLE_API"
        #     )

        return self.client

    def _full_url(self, path: str) -> str:
        return f"{self.server.rstrip('/')}/{path.lstrip('/')}"

    def get_info(self):
        url = self._full_url('/info/me.json')
        resp = self.client.async_request('GET', url)
        if resp is None:
            return None
        if getattr(resp, 'status_code', None) == 200:
            try:
                return resp.json()
            except Exception:
                return None
        return None

    def get_cameras(self) -> httpx.Response:
        """Fetch the list of cameras from the Opencast server.

        Returns:
            httpx.Response: The HTTP response containing the camera data.
        """
        url = f"{self.server}/capture-admin/agents.json"
        client = self.create_digest_client()
        response = client.get(url)
        response.raise_for_status()
        return response

    def get_cainfo(self) -> httpx.Response:
        """Fetch the cainfo of all cameras from Opencast Server.

        Retuens:
            httpx.Response: The HTTP response containing capture agent information.
        """
        url = f"{self.server}/mrtg/dashboard/cainfo.json"
        client = self.create_digest_client()
        response = client.get(url)
        response.raise_for_status()
        return response

    def get_capture_agent_status(self) -> httpx.Response:
        """Fetch the status of a specific capture agent from Opencast Server.

        Returns:
            httpx.Response: The HTTP response containing the capture agent status.
        """
        url = f"{self.server}/admin-ng/capture-agents/agents.json"
        client = self.create_digest_client()
        response = client.get(url)
        response.raise_for_status()
        return response

    def get_recordings(self, limit: int = -1) -> httpx.Response:
        """
        Fetch scheduled events/recordings for **today** in the fixed window:
        08:00:00.000Z to 21:59:59.999Z (UTC).

        Args:
            limit: Max number of results (-1 = no limit)

        Returns:
            httpx.Response object from the Opencast admin-ng/events endpoint
        """
        now_utc = datetime.now(timezone.utc)

        # Start: today at 08:00:00.000 UTC
        start_of_day = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)

        # End: today at 21:59:59.999 UTC
        end_of_day = now_utc.replace(hour=21, minute=59, second=59, microsecond=999000)

        # Ensure end is still on the same day (edge case if called very late)
        if end_of_day < start_of_day:
            end_of_day = start_of_day + timedelta(hours=13, minutes=59, seconds=59, milliseconds=999)

        # ISO 8601 strings with Z and millisecond precision
        start_str = start_of_day.isoformat(timespec="milliseconds")
        end_str   = end_of_day.isoformat(timespec="milliseconds")

        # Final filter string (without "startDate:" prefix here — added directly in URL)
        date_range = f"{start_str}%2F{end_str}"

        # Build URL with the exact format you want
        url = (
            f"{self.server}/admin-ng/event/events.json"
            f"?limit={limit}"
            f"&filter=startDate:{date_range}"
        )

        print(f"Fetching today's scheduled events with URL: {url}")
        print(f"  Date range: {start_str} / {end_str}")

        client = self.create_digest_client()

        response = client.get(url)
        response.raise_for_status()

        # Return the full URL string (as requested)
        return url