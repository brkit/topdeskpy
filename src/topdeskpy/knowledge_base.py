"""Knowledge Base operations before and after the folder explorer migration."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from ._transport import JsonObject, Params, Transport, segment


class KnowledgeBase:
    """Use the services endpoint at the installation origin, outside /tas/api."""

    _base = "/services/knowledge-base-v1"

    def __init__(
        self, transport: Transport, *, mode: Literal["legacy", "folders"] = "folders"
    ) -> None:
        if mode not in ("legacy", "folders"):
            raise ValueError("mode must be 'legacy' or 'folders'")
        self._transport = transport
        self._folder_explorer = mode == "folders"

    def list(self, *, params: Params | None = None) -> JsonObject:
        """Return the item/prev/next envelope, filtered by the requested language."""
        return self._transport.object("GET", f"{self._base}/knowledgeItems", params=params)

    def iter(self, *, params: Params | None = None, page_size: int = 100) -> Iterator[JsonObject]:
        """Iterate the singular item array with start/page_size pagination."""
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        query = dict(params or {})
        start = int(query.get("start") or 0)
        while True:
            query.update(start=start, page_size=page_size)
            page = self.list(params=query)
            rows = self._transport.collection(page, "item", f"{self._base}/knowledgeItems")
            yield from rows
            if not rows or not page.get("next"):
                return
            start += len(rows)

    def get(self, identifier: str, *, params: Params | None = None) -> JsonObject:
        """Get by UUID or complete item number, such as KI 0211."""
        return self._transport.object("GET", self._item(identifier), params=params)

    def folders(self, *, params: Params | None = None) -> JsonObject:
        """List folders on installations that have migrated to the folder explorer."""
        return self._transport.object("GET", f"{self._base}/folders", params=params)

    def migrated(self) -> JsonObject:
        """Probe migration state where supported (documented until December 2026)."""
        return self._transport.object("GET", f"{self._base}/explorer/migrated")

    def create(self, data: JsonObject) -> JsonObject:
        """Create with translation and optional parent; return id and number.

        Legacy parents reference knowledge items. After migration, a parent
        referencing a folder is mandatory.
        """
        return self._transport.object(
            "POST",
            f"{self._base}/knowledgeItems",
            json=data,
            headers={"Content-Type": "application/x.topdesk-kb-create-ki-v1+json"},
        )

    def update(self, identifier: str, data: JsonObject) -> None:
        """Update metadata. Use update_translation to change title or content."""
        self._transport.request(
            "PATCH" if self._folder_explorer else "POST",
            self._item(identifier),
            json=data,
            headers={"Content-Type": "application/x.topdesk-kb-update-ki-v1+json"},
        )

    def update_translation(self, identifier: str, language: str, data: JsonObject) -> None:
        self._transport.request(
            "PATCH" if self._folder_explorer else "POST",
            f"{self._item(identifier)}/translations/{segment(language)}",
            json=data,
            headers={"Content-Type": "application/x.topdesk-kb-update-translation-v1+json"},
        )

    def create_translation(self, identifier: str, language: str, data: JsonObject) -> None:
        """Create a translation from a content mapping containing a title."""
        path = f"{self._item(identifier)}/translations"
        body = {"language": language, "content": data}
        if self._folder_explorer:
            path += f"/{segment(language)}"
            body = data
        self._transport.request(
            "POST",
            path,
            json=body,
            headers={"Content-Type": "application/x.topdesk-kb-create-translation-v1+json"},
        )

    def delete_translation(self, identifier: str, language: str) -> None:
        """Delete a translation; TOPdesk forbids deleting the last translation."""
        self._transport.request(
            "DELETE", f"{self._item(identifier)}/translations/{segment(language)}"
        )

    def archive(self, identifier: str) -> None:
        """Archive an item; the API provides no permanent item deletion."""
        self._transport.request("POST", f"{self._item(identifier)}/archive")

    def unarchive(self, identifier: str) -> None:
        self._transport.request("POST", f"{self._item(identifier)}/unarchive")

    def _item(self, identifier: str) -> str:
        return f"{self._base}/knowledgeItems/{segment(identifier)}"
