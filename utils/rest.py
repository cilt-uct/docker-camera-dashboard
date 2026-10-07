#!/usr/bin/python3

# Rest client used across scripts

# Usage examples
# - Synchronous:
#     with RestClient(base_url, auth=(user, pw)) as client:
#         resp = client.request('GET', url)
# - Asynchronous:
#     async with RestClient(base_url, auth=(user, pw)) as client:
#         resp = await client.async_request('GET', url)

import httpx
import logging
import time
import asyncio
from typing import Optional

# Status codes that should trigger a retry
_STATUS_FORCELIST = {429, 500, 502, 503, 504}


def _calc_backoff(attempt: int, backoff_factor: float) -> float:
    """Exponential backoff calculation"""
    return backoff_factor * (2 ** (attempt - 1))


class RestClient:
    """A small client that wraps httpx (and falls back to requests for Digest auth) to make
    sync and async requests with retries, timeout and optional headers.

    Usage:
        client = RestClient(base_url, auth=(user, pass), auth_type='basic')
        resp = client.request('POST', '/path', data=...)
        await client.async_request('GET', '/path')
    """

    def __init__(self, base_url: Optional[str] = None,
                 auth: Optional[tuple] = None, auth_type: str = 'basic',
                 timeout: float = 10, retries: int = 3, backoff_factor: float = 0.3,
                 headers: Optional[dict] = None):

        self.base_url = base_url.rstrip('/') if isinstance(base_url, str) else base_url
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff_factor = backoff_factor

        DEFAULT_USER_AGENT = {'User-Agent': 'CILT Scripts/2026.01.09'}
        self.headers = {**DEFAULT_USER_AGENT, **(headers or {})}

        self._use_requests_digest = False
        self._requests_session = None
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

        if auth:
            user, password = auth[0], auth[1]
            if str(auth_type).lower() == 'digest':
                # Prefer httpx's DigestAuth if available, otherwise fallback to requests for digest
                try:
                    from httpx import DigestAuth as _HttpxDigestAuth
                    self._auth = _HttpxDigestAuth(user, password)
                except Exception:
                    # retry with basic request class
                    import requests
                    from requests.auth import HTTPDigestAuth
                    from requests.adapters import HTTPAdapter
                    from urllib3.util.retry import Retry

                    self._use_requests_digest = True
                    self._requests_auth = HTTPDigestAuth(user, password)

                    # prepare requests session with retries
                    retry_strategy = Retry(
                        total=self.retries,
                        backoff_factor=self.backoff_factor,
                        status_forcelist=list(_STATUS_FORCELIST),
                        allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"],
                    )
                    adapter = HTTPAdapter(max_retries=retry_strategy)
                    self._requests_session = requests.Session()
                    self._requests_session.auth = self._requests_auth
                    self._requests_session.mount("https://", adapter)
                    self._requests_session.mount("http://", adapter)
                    self._requests_session.headers.update(self.headers)
                    self._requests_session.timeout = self.timeout
            else:
                self._auth = httpx.BasicAuth(user, password)
        else:
            self._auth = None

        if not self._use_requests_digest:
            # create a persistent client for sync requests
            self._client = httpx.Client(auth=self._auth, timeout=self.timeout, headers=self.headers)

    def request(self, method: str, url: str, params: Optional[dict] = None, payload_data=None, files=None, headers=None, timeout: Optional[float] = None) -> Optional[object]:
        """Synchronous request."""
        method = (method or 'GET').upper()
        if method == 'GET' and (files is not None or payload_data is not None):
            method = 'POST'

        headers = {**(self.headers or {}), **(headers or {})}
        timeout = timeout or self.timeout

        if self._use_requests_digest:
            # Use requests.Session for Digest auth
            kwargs = {'headers': headers}
            if params is not None:
                kwargs['params'] = params
            if files is not None:
                kwargs['files'] = files
            elif payload_data is not None:
                kwargs['data'] = payload_data

            for attempt in range(1, self.retries + 1):
                try:
                    resp = self._requests_session.request(method, url, timeout=timeout, **kwargs)

                    if resp.status_code in _STATUS_FORCELIST:
                        logging.warning("API call %s returned transient status %s (attempt %s/%s)", url, resp.status_code, attempt, self.retries)
                        if attempt == self.retries:
                            return resp
                        time.sleep(_calc_backoff(attempt, self.backoff_factor))
                        continue

                    if not getattr(resp, 'ok', False):
                        try:
                            body = resp.text
                        except Exception:
                            body = "<unreadable body>"
                        logging.warning("API call %s returned status %s; body: %s", url, resp.status_code, body)

                    return resp

                except Exception as err:
                    logging.exception("API call %s failed (attempt %s/%s): %s", url, attempt, self.retries, err)
                    if attempt == self.retries:
                        return None
                    time.sleep(_calc_backoff(attempt, self.backoff_factor))

        else:
            # Use httpx.Client
            client = self._client or httpx.Client(auth=self._auth, timeout=timeout, headers=headers)
            for attempt in range(1, self.retries + 1):
                try:
                    kwargs = {}
                    if params is not None:
                        kwargs['params'] = params
                    if headers:
                        kwargs['headers'] = headers
                    if files is not None:
                        kwargs['files'] = files
                    elif payload_data is not None:
                        kwargs['data'] = payload_data

                    response = client.request(method, url, **kwargs)

                    if response.status_code in _STATUS_FORCELIST:
                        logging.warning("API call %s returned transient status %s (attempt %s/%s)", url, response.status_code, attempt, self.retries)
                        if attempt == self.retries:
                            return response
                        time.sleep(_calc_backoff(attempt, self.backoff_factor))
                        continue

                    if not response.is_success:
                        try:
                            body = response.text
                        except Exception:
                            body = "<unreadable body>"
                        logging.warning("API call %s returned status %s; body: %s", url, response.status_code, body)

                    return response

                except httpx.RequestError as err:
                    logging.exception("API call %s failed (attempt %s/%s): %s", url, attempt, self.retries, err)
                    if attempt == self.retries:
                        return None
                    time.sleep(_calc_backoff(attempt, self.backoff_factor))

    async def async_request(self, method: str, url: str, params: Optional[dict] = None, payload_data=None, files=None, headers=None, timeout: Optional[float] = None) -> Optional[object]:
        """Asynchronous request (awaitable). If Digest auth is used and requests is the fallback, runs sync calls in a thread."""
        method = (method or 'GET').upper()
        if method == 'GET' and (files is not None or payload_data is not None):
            method = 'POST'

        headers = {**(self.headers or {}), **(headers or {})}
        timeout = timeout or self.timeout

        if self._use_requests_digest:
            # run blocking requests call in a thread
            return await asyncio.to_thread(self.request, method, url, payload_data, files, headers, timeout)

        # Use httpx.AsyncClient
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(auth=self._auth, timeout=timeout, headers=headers)

        for attempt in range(1, self.retries + 1):
            try:
                kwargs = {}
                if headers:
                    kwargs['headers'] = headers
                if files is not None:
                    kwargs['files'] = files
                elif payload_data is not None:
                    kwargs['data'] = payload_data

                response = await self._async_client.request(method, url, **kwargs)

                if response.status_code in _STATUS_FORCELIST:
                    logging.warning("API call %s returned transient status %s (attempt %s/%s)", url, response.status_code, attempt, self.retries)
                    if attempt == self.retries:
                        return response
                    await asyncio.sleep(_calc_backoff(attempt, self.backoff_factor))
                    continue

                if not response.is_success:
                    try:
                        body = response.text
                    except Exception:
                        body = "<unreadable body>"
                    logging.warning("API call %s returned status %s; body: %s", url, response.status_code, body)

                return response

            except httpx.RequestError as err:
                logging.exception("API call %s failed (attempt %s/%s): %s", url, attempt, self.retries, err)
                if attempt == self.retries:
                    return None
                await asyncio.sleep(_calc_backoff(attempt, self.backoff_factor))

    def get(self, url: str, params: Optional[dict] = None, headers=None, timeout=None):
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                # never let closing the client crash the app
                pass
        if self._requests_session is not None:
            try:
                self._requests_session.close()
            except Exception:
                # never let closing the session crash the app
                pass

    async def aclose(self):
        if self._async_client is not None:
            try:
                await self._async_client.aclose()
            except Exception:
                # never let closing the async client crash the app
                pass

    # Context manager support (sync and async)
    def __enter__(self):
        # ensure a sync client is available when entering the context
        if not self._use_requests_digest and self._client is None:
            self._client = httpx.Client(auth=self._auth, timeout=self.timeout, headers=self.headers)
        return self

    def __exit__(self, exc_type, exc, tb):
        # always close resources on exit; do not suppress exceptions
        try:
            self.close()
        except Exception:
            logging.exception("Error closing RestClient in __exit__")
        return False

    async def __aenter__(self):
        # ensure an async client is available when entering the async context
        if not self._use_requests_digest and self._async_client is None:
            self._async_client = httpx.AsyncClient(auth=self._auth, timeout=self.timeout, headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            await self.aclose()
        except Exception:
            logging.exception("Error closing RestClient in __aexit__")
        return False
