"""A small JSON client for the accounts server (server/), used when DMG_API_URL is set."""

import json
import os
import urllib.error
import urllib.request


def api_url() -> str:
    return os.environ.get("DMG_API_URL", "").strip().rstrip("/")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class Api:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url
        self.token = token

    def get(self, path: str) -> dict:
        return self._call("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._call("POST", path, body or {})

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read()).get("error", "")
            except ValueError:
                message = ""
            raise ApiError(message or f"Server error ({e.code}). Try again later.", e.code) from e
        except OSError as e:
            raise ApiError("No connection to the server. Check your internet and try again.") from e
