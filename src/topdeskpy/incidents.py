"""Operator-facing incident management API."""

import builtins
from collections.abc import Iterator, Mapping
from typing import Any

from ._transport import JsonObject, Params, Transport, segment


class Incidents:
    """Read, create, update, and archive incidents as an operator."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(self, *, params: Params | None = None) -> builtins.list[JsonObject]:
        """Return one page using pageStart/pageSize and optional FIQL query."""
        return self._transport.objects("GET", "incidents", params=params)

    def iter(self, *, params: Params | None = None, page_size: int = 100) -> Iterator[JsonObject]:
        """Yield all matching incidents using offset pagination."""
        if not 1 <= page_size <= 10000:
            raise ValueError("page_size must be between 1 and 10000")
        return self._transport.iter_offset("incidents", params=params, page_size=page_size)

    def get(self, identifier: str) -> JsonObject:
        """Return an incident by UUID."""
        return self._transport.object("GET", self._path(identifier))

    def get_by_number(self, number: str) -> JsonObject:
        """Return an incident by its human-readable number."""
        return self._transport.object("GET", f"incidents/number/{segment(number)}")

    def create(self, data: Mapping[str, Any]) -> JsonObject:
        """Create an incident using TOPdesk field names and reference objects."""
        return self._transport.object("POST", "incidents", json=dict(data))

    def update(self, identifier: str, data: Mapping[str, Any]) -> JsonObject:
        """Update fields by UUID; data is an object, not JSON Patch operations."""
        return self._transport.object("PATCH", self._path(identifier), json=dict(data))

    def update_by_number(self, number: str, data: Mapping[str, Any]) -> JsonObject:
        """Update fields using an incident number."""
        return self._transport.object(
            "PATCH", f"incidents/number/{segment(number)}", json=dict(data)
        )

    def archive(self, identifier: str, reason: Mapping[str, Any] | None = None) -> JsonObject:
        """Archive an incident and its partials, optionally specifying a reason."""
        return self._transport.object(
            "PUT",
            self._path(identifier) + "/archive",
            json=dict(reason) if reason is not None else None,
        )

    def unarchive(self, identifier: str, *, unarchive_partials: bool = True) -> JsonObject:
        """Unarchive an incident and optionally its partials."""
        return self._transport.object(
            "PUT",
            self._path(identifier) + "/unarchive",
            params={"unarchive_partials": unarchive_partials},
        )

    def add_action(
        self, identifier: str, text: str, *, invisible_for_caller: bool = False
    ) -> JsonObject:
        """Append action text by updating the incident."""
        return self.update(
            identifier, {"action": text, "actionInvisibleForCaller": invisible_for_caller}
        )

    def actions(
        self, identifier: str, *, params: Params | None = None
    ) -> builtins.list[JsonObject]:
        """Return one page of action history using start/page_size parameters."""
        return self._transport.objects("GET", self._path(identifier) + "/actions", params=params)

    def requests(
        self, identifier: str, *, params: Params | None = None
    ) -> builtins.list[JsonObject]:
        """Return one page of request history using start/page_size parameters."""
        return self._transport.objects("GET", self._path(identifier) + "/requests", params=params)

    def iter_actions(
        self, identifier: str, *, params: Params | None = None, page_size: int = 100
    ) -> Iterator[JsonObject]:
        """Yield action history across all pages."""
        return self._iter_history(identifier, "actions", params, page_size)

    def iter_requests(
        self, identifier: str, *, params: Params | None = None, page_size: int = 100
    ) -> Iterator[JsonObject]:
        """Yield request history across all pages."""
        return self._iter_history(identifier, "requests", params, page_size)

    def lookup(self, name: str, *, params: Params | None = None) -> builtins.list[JsonObject]:
        """Return a supported incident dropdown or lookup page."""
        supported = {
            "call_types",
            "durations",
            "entry_types",
            "impacts",
            "priorities",
            "statuses",
            "categories",
            "subcategories",
            "closure_codes",
            "urgencies",
            "callers",
            "operators",
            "operatorgroups",
        }
        if name not in supported:
            raise ValueError(f"Unsupported incident lookup: {name}")
        suffix = "/lookup" if name in {"callers", "operators", "operatorgroups"} else ""
        return self._transport.objects("GET", f"incidents/{name}{suffix}", params=params)

    def _iter_history(
        self, identifier: str, kind: str, params: Params | None, page_size: int
    ) -> Iterator[JsonObject]:
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        return self._transport.iter_offset(
            self._path(identifier) + f"/{kind}",
            params=params,
            page_size=page_size,
            start_key="start",
            size_key="page_size",
        )

    @staticmethod
    def _path(identifier: str) -> str:
        return f"incidents/id/{segment(identifier)}"
