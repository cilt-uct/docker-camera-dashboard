import httpx
import logging

from utils.rest import RestClient

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

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
                # if parsing of json fails, return None
                return None
        return None

    def get_capture_agent_capabilities(self) -> httpx.Response:
        """Fetch the list of cameras from the Opencast server.

        Returns:
            httpx.Response: The HTTP response containing the camera data.
        """
        url = f"{self.server}/capture-admin/agents.json"
        client = self.create_digest_client()
        response = client.get(url)
        response.raise_for_status()
        return response

    def get_ca_names(self) -> httpx.Response:
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

    def get_events(self, filter:str = '', seriesId:str = '',
                    start_date:str = '', end_date:str = '',
                    sort:str = 'date:ASC,title:ASC',
                    withPublications:bool = True,
                    withAcl:bool = False,
                    withMetadata:bool = False,
                    withScheduling:bool = False,
                    onlyWithWriteAccess:bool = False,
                    sign:bool = False,
                    offset:int = 0,
                    limit:int = 1000):

        filter_ar = []
        if filter:
            filter_ar.append(filter)

        if seriesId:
            filter_ar.append(f"series:{seriesId}")

        if start_date and end_date:
            filter_ar.append(f"start:{start_date}/{end_date}")

        filter = ','.join(filter_ar)

        params = {
            "filter": filter,
            "sort": sort,
            "withpublications": "true" if withPublications else "false",
            "withacl": "true" if withAcl else "false",
            "withmetadata": "true" if withMetadata else "false",
            "withscheduling": "true" if withScheduling else "false",
            "onlyWithWriteAccess": "true" if onlyWithWriteAccess else "false",
            "sign": "true" if sign else "false",
            "offset": offset,
            "limit": limit
        }

        client = self.create_digest_client()
        resp = client.get(self._full_url(f'{self.server}/api/events'), params=params)
        if resp and getattr(resp, 'status_code', None) == 200:
            try:
                return resp.json()
            except Exception:
                # if parsing of json fails, return None
                return None

        return None

class CaptureAgent:
    def __init__(self, data: Dict[str, Any]):
        self._raw = data

        self.name: str = data.get("name")
        self.state: str = data.get("state")
        self.url: str = data.get("url")
        self.time_since_last_update: int = data.get("time-since-last-update", 0)

        try:
            last_dt = datetime.now() - timedelta(seconds=self.time_since_last_update)
            self.last_updated = last_dt.strftime('%Y-%m-%d %H:%M:%S')
        except OverflowError:
            self.last_updated = None

        self._capabilities: Dict[str, Any] = {}

        raw_items = data.get("capabilities", {}).get("item", [])

        # ---- NORMALIZATION ----
        if isinstance(raw_items, dict):
            raw_items = [raw_items]  # single item → list
        elif isinstance(raw_items, str):
            raw_items = []  # garbage case safeguard

        # ---- SAFE PARSE ----
        for item in raw_items:
            if not isinstance(item, dict):
                continue  # skip junk safely

            key = item.get("key")
            value = item.get("value")

            if key:
                self._capabilities[key] = value

    # ---- API ----

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self._raw.get(key, default)

    def get_capability(self, key: str, default: Optional[Any] = None) -> Any:
        return self._capabilities.get(key, default)

    def has_capability(self, key: str) -> bool:
        return key in self._capabilities

    def all_capabilities(self) -> Dict[str, Any]:
        return self._capabilities

    def device_names(self) -> list[str]:
        names = self.get_capability("capture.device.names", "")
        return [n.strip() for n in names.split(",") if n]

    def __repr__(self):
        return f"<CaptureAgent name={self.name} state={self.state}>"

    def get_dict(self, display:str = ''):
        return {
            'name' : self.name,
            'display': display if display else self.name,
            'state' : self.state,
            'url' : self.url,
            'time_since_last_update' : self.time_since_last_update,
            'last_updated': self.last_updated if self.last_updated else ''
        }
