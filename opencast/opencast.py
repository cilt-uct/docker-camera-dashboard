import httpx
from httpx import DigestAuth

class Opencast(object):

    def __init__(
        self,
        server: str,
        username: str,
        password: str
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

    def create_digest_client(self) -> httpx.Client:
        """Create an HTTPX client with Digest Authentication.

        Returns:
            httpx.Client: An HTTPX client configured for Digest Auth.
        """
        auth = DigestAuth(self.username, self.password)
        client = httpx.Client(auth=auth)
        return client

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