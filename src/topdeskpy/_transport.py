"""Shared HTTP behavior; resource modules handle their own API conventions."""

from collections.abc import Iterator, Mapping
from ssl import SSLContext
from typing import Any, TypeAlias, cast
from urllib.parse import quote, urlsplit

import httpx2

from .exceptions import APIError, UnexpectedResponseError

# TOPdesk fields and custom asset schemas vary by installation. Keep response keys
# intact rather than dropping unknown fields during model validation.
JsonObject: TypeAlias = dict[str, Any]
Params: TypeAlias = Mapping[str, str | int | float | bool | None]


def segment(value: str) -> str:
    """Encode an identifier as one URL path segment."""
    if not value or value in {".", ".."}:
        raise ValueError("An identifier must be nonempty and cannot be '.' or '..'")
    return quote(value, safe="")


class Transport:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float | httpx2.Timeout = 30.0,
        verify: bool | SSLContext = True,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        url = urlsplit(base_url)
        if url.scheme not in {"https", "http"} or not url.hostname:
            raise ValueError("base_url must be an absolute HTTP(S) installation URL")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url must not contain credentials, a query, or a fragment")
        path = url.path.rstrip("/")
        if path not in {"", "/tas/api"}:
            raise ValueError("base_url must be the installation origin or end with /tas/api")
        if not username or not password:
            raise ValueError("username and application password must be nonempty")
        self.origin = f"{url.scheme}://{url.netloc}"
        self.base_url = self.origin + "/tas/api/"
        self.client = httpx2.Client(
            auth=httpx2.BasicAuth(username, password),
            timeout=timeout,
            verify=verify,
            transport=transport,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "topdeskpy/0.2.0"},
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Params | None = None,
        json: Mapping[str, Any] | list[Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        """Send one request. Writes are never automatically retried."""
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc:
            if (parsed.scheme, parsed.netloc) != (
                urlsplit(self.origin).scheme,
                urlsplit(self.origin).netloc,
            ):
                raise ValueError("Refusing to send credentials to another origin")
            url = path
        elif path.startswith("/"):
            url = self.origin + path
        else:
            url = self.base_url + path
        if urlsplit(url).path.split("/")[1:3] not in [
            ["tas", "api"],
            ["services", "knowledge-base-v1"],
        ]:
            raise ValueError("Request path is outside the supported TOPdesk APIs")
        query = {key: value for key, value in (params or {}).items() if value is not None}
        response = self.client.request(
            method, url, params=query or None, json=json, headers=headers
        )
        if not response.is_success:
            raise APIError(response)
        return response

    @staticmethod
    def decode(response: httpx2.Response) -> Any:
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise UnexpectedResponseError(
                f"Expected JSON from {response.request.url.path}, "
                f"got {response.headers.get('content-type')}"
            ) from error

    def object(self, method: str, path: str, **kwargs: Any) -> JsonObject:
        response = self.request(method, path, **kwargs)
        data = self.decode(response)
        if not isinstance(data, dict):
            raise UnexpectedResponseError(
                f"Expected a JSON object from {response.request.url.path}"
            )
        return cast(JsonObject, data)

    def objects(self, method: str, path: str, **kwargs: Any) -> list[JsonObject]:
        response = self.request(method, path, **kwargs)
        data = self.decode(response)
        if data is None:
            return []
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise UnexpectedResponseError(
                f"Expected a JSON object array from {response.request.url.path}"
            )
        return cast(list[JsonObject], data)

    @staticmethod
    def collection(data: JsonObject, key: str, path: str) -> list[JsonObject]:
        """Read an object array from one of TOPdesk's collection envelopes."""
        rows = data.get(key)
        if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
            raise UnexpectedResponseError(f"Expected a '{key}' object array from {path}")
        return cast(list[JsonObject], rows)

    def iter_offset(
        self,
        path: str,
        *,
        params: Params | None = None,
        page_size: int = 100,
        start_key: str = "pageStart",
        size_key: str = "pageSize",
    ) -> Iterator[JsonObject]:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        query = dict(params or {})
        offset = int(query.get(start_key) or 0)
        while True:
            query.update({start_key: offset, size_key: page_size})
            response = self.request("GET", path, params=query)
            data = self.decode(response)
            if data is None:
                return
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise UnexpectedResponseError(f"Expected a JSON object array from {path}")
            yield from data
            if response.status_code != 206:
                return
            if not data:
                raise UnexpectedResponseError(f"Empty partial page from {path}")
            offset += len(data)
