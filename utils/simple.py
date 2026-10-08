import httpx
import logging
import json
import re

from bs4 import BeautifulSoup
from datetime import datetime

from .rest import RestClient

logger = logging.getLogger(__name__)

try:
    import json5  # handles unquoted keys, trailing commas, comments
except ImportError:
    json5 = None

PAGE_URL = "https://srvubuopc301.uct.ac.za/"  # change to your page

class SimpleHTML(object):

    def __init__(
        self,
        username: str,
        password: str,
        # connection_name:str,

        timeout: float = 5,
        retries: int = 3,
        backoff_factor: float = 0.3,
        headers: dict = None
        ) -> None:
        """Instantiates library.

        Args:
            username (str): The username to use for authentication.
            password (str): The password to use for authentication.
        """
        self.username = username
        self.password = password

        self.timeout = timeout
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.headers = headers or {}

    @classmethod
    def get_classname(cls):
        return cls.__name__

    def create_client(self):

        DEFAULT_HEADER = {
            'User-Agent': f'{self.get_classname()}/{datetime.now().strftime("%Y-%m-%d")}'
        }

        headers = {**DEFAULT_HEADER, **self.headers}
        auth = None
        auth_type = None
        if self.username and self.password:
            auth = (self.username, self.password)
            auth_type = 'basic'

        self.client = RestClient(
            auth=auth,
            auth_type=auth_type,
            timeout=self.timeout,
            retries=self.retries,
            backoff_factor=self.backoff_factor,
            headers=headers
        )
        return self.client

    def fetch_html(self, url: str ):
        client = self.create_client()
        print('Fetching URL:', url)
        resp = client.get(url)
        if resp is None:
            return None
        if getattr(resp, 'status_code', None) == 200:
            try:
                return resp.text
            except Exception:
                # if parsing of json fails, return None
                return None
        return None


    @staticmethod
    def find_script_with(html: str, marker: str = "ar = [") -> str:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            if script.get("src"):
                continue  # skip external scripts (jquery etc.)
            text = script.string or script.get_text()
            if text and re.search(r"\bar\s*=\s*\[", text):
                return text
        raise ValueError(f"No inline <script> containing '{marker}' found")

    @staticmethod
    def extract_array_literal(js: str, var: str = "ar") -> str:
        """Return the raw '[ ... ]' text assigned to `var`, matching brackets
        while ignoring brackets inside string literals."""
        m = re.search(rf"\b{re.escape(var)}\s*=\s*\[", js)
        if not m:
            raise ValueError(f"'{var} = [' not found")
        start = m.end() - 1  # position of '['
        depth, i, quote = 0, start, None
        while i < len(js):
            c = js[i]
            if quote:
                if c == "\\":
                    i += 1  # skip escaped char
                elif c == quote:
                    quote = None
            elif c in "\"'`":
                quote = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return js[start:i + 1]
            i += 1
        raise ValueError("Unbalanced brackets in array literal")

    @staticmethod
    def js_literal_to_python(literal: str):
        if json5:
            return json5.loads(literal)

        # Fallback: minimal JS -> JSON conversion (fine for this simple data)
        s = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)\s*:", r'\1"\2":', literal)  # quote keys
        s = re.sub(r",\s*([}\]])", r"\1", s)                                 # trailing commas
        return json.loads(s)

    def get_pyca_servers(self, url: str) -> list[dict]:

        try:
            html = self.fetch_html(url)
            script = self.find_script_with(html)
            literal = self.extract_array_literal(script, "ar")
            result = self.js_literal_to_python(literal)
            return result

        except Exception as e:
            print(f"Error fetching HTML from {url}: {e}")
            return []

    def ping(self, url: str, timeout: float = 5) -> tuple[bool, str]:
        """Return (ok, info) for a simple 'does this page exist' check."""
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.head(url, follow_redirects=True)
                if r.status_code in (405, 501):  # HEAD not supported -> try GET
                    r = client.get(url, follow_redirects=True)
            return r.is_success, str(r.status_code)
        except httpx.RequestError as e:
            return False, type(e).__name__
