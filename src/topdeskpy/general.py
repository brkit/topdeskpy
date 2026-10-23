"""General TOPdesk API resources."""

from collections.abc import Iterator
from typing import cast

from ._transport import JsonObject, Params, Transport, segment
from .exceptions import UnexpectedResponseError


class General:
    """Read shared metadata, categories, reasons, and service windows."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def version(self) -> JsonObject:
        """Return the API version."""
        return self._transport.object("GET", "version")

    def product_version(self) -> JsonObject:
        """Return the TOPdesk product version."""
        return self._transport.object("GET", "productVersion")

    def categories(self, *, params: Params | None = None) -> JsonObject:
        """Return the category envelope, including its item and next fields."""
        return self._transport.object("GET", "categories", params=params)

    def iter_categories(self, *, params: Params | None = None) -> Iterator[JsonObject]:
        """Yield categories, following the envelope's next link when present."""
        path = "categories"
        seen: set[str] = set()
        while path:
            if path in seen:
                raise ValueError("Category pagination returned a repeated next link")
            seen.add(path)
            page = self._transport.object("GET", path, params=params)
            yield from self._transport.collection(page, "item", path)
            path = page.get("next") or ""
            params = None

    def archiving_reasons(self) -> list[JsonObject]:
        """Return available archiving reasons."""
        return self._transport.objects("GET", "archiving-reasons")

    def timespent_reasons(self) -> list[JsonObject]:
        """Return available time registration reasons."""
        return self._transport.objects("GET", "timespent-reasons")

    def service_windows(
        self, *, top: int = 1000, name: str | None = None, archived: bool | None = None
    ) -> list[JsonObject]:
        """Return up to top service windows; this endpoint has no offset."""
        if not 1 <= top <= 10000:
            raise ValueError("top must be between 1 and 10000")
        response = self._transport.request(
            "GET", "serviceWindow/lookup/", params={"$top": top, "name": name, "archived": archived}
        )
        data = self._transport.decode(response)
        # Older TOPdesk releases wrap this list in a results envelope.
        if isinstance(data, dict):
            return self._transport.collection(data, "results", "serviceWindow/lookup/")
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise UnexpectedResponseError("Expected a service window array")
        return cast(list[JsonObject], data)

    def service_window(self, identifier: str) -> JsonObject:
        """Return a service window by ID."""
        return self._transport.object("GET", f"serviceWindow/lookup/{segment(identifier)}")
