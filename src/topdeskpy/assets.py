"""Asset Management operations with template-specific field mappings."""

from __future__ import annotations

import builtins
import warnings
from collections.abc import Iterator

from ._transport import JsonObject, Params, Transport, segment
from .exceptions import PartialUpdateWarning, UnexpectedResponseError


class Assets:
    """Access assets relative to the TOPdesk API base path."""

    _headers = {"Accept": "application/x.topdesk-am-assets-v2+json"}

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(self, *, params: Params | None = None) -> JsonObject:
        """Return the columns/dataSet envelope, including optional count metadata."""
        return self._transport.object(
            "GET", "assetmgmt/assets", params=params, headers=self._headers
        )

    def iter(self, *, params: Params | None = None, page_size: int = 100) -> Iterator[JsonObject]:
        """Iterate dataSet rows using Asset Management offset pagination."""
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        query = dict(params or {})
        if "lastSeenName" in query or "lastSeenOrderbyValue" in query:
            raise ValueError("Seek pagination parameters cannot be used with offset iteration")
        start = int(query.get("pageStart") or 0)
        while True:
            query.update(pageStart=start, pageSize=page_size)
            path = "assetmgmt/assets"
            response = self._transport.request("GET", path, params=query, headers=self._headers)
            page = self._transport.decode(response)
            if not isinstance(page, dict):
                raise UnexpectedResponseError(f"Expected a JSON object from {path}")
            rows = self._transport.collection(page, "dataSet", path)
            yield from rows
            if response.status_code != 206:
                return
            if not rows:
                raise UnexpectedResponseError(f"Empty partial page from {path}")
            start += len(rows)

    def get(self, asset_id: str) -> JsonObject:
        return self._transport.object("GET", f"assetmgmt/assets/{segment(asset_id)}")

    def templates(self, *, params: Params | None = None) -> JsonObject:
        return self._transport.object("GET", "assetmgmt/templates", params=params)

    def blank(self, template_id: str) -> JsonObject:
        """Inspect the template's mandatory fields before creating an asset."""
        return self._transport.object(
            "GET",
            "assetmgmt/assets/blank",
            params={"templateId": template_id},
        )

    def _save(self, path: str, data: JsonObject) -> JsonObject:
        response = self._transport.request("POST", path, json=data)
        if response.status_code == 202:
            warnings.warn(
                "TOPdesk saved the asset but ignored one or more unknown fields",
                PartialUpdateWarning,
                stacklevel=3,
            )
        result = self._transport.decode(response)
        if not isinstance(result, dict):
            raise UnexpectedResponseError("Expected an asset JSON object")
        return result

    def create(self, data: JsonObject) -> JsonObject:
        """Create with type_id and all mandatory template-specific field values."""
        return self._save("assetmgmt/assets", data)

    def update(self, asset_id: str, data: JsonObject) -> JsonObject:
        """Update fields; include the current @etag for concurrency checking."""
        return self._save(f"assetmgmt/assets/{segment(asset_id)}", data)

    def delete(self, asset_ids: builtins.list[str]) -> JsonObject:
        """Return deleted/failed/missing/unauthorized lists; inspect every outcome."""
        return self._transport.object("POST", "assetmgmt/assets/delete", json={"unids": asset_ids})

    def archive(self, asset_id: str, reason_id: str) -> JsonObject:
        return self._transport.object(
            "POST",
            f"assetmgmt/assets/{segment(asset_id)}/archive",
            json={"reasonId": reason_id},
        )

    def unarchive(self, asset_id: str) -> JsonObject:
        return self._transport.object("POST", f"assetmgmt/assets/{segment(asset_id)}/unarchive")
