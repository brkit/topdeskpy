"""Public entry point for the synchronous TOPdesk API client."""

from ssl import SSLContext
from types import TracebackType
from typing import Literal

import httpx2

from ._transport import Transport
from .assets import Assets
from .general import General
from .incidents import Incidents
from .knowledge_base import KnowledgeBase


class TopdeskClient:
    """A reusable connection pool with resource-specific TOPdesk operations.

    Pass the installation origin or its ``/tas/api`` URL and an operator's
    application password. TLS certificates are verified by default. Use a custom
    ``SSLContext`` for private certificate authorities or the OS trust store.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float | httpx2.Timeout = 30.0,
        verify: bool | SSLContext = True,
        knowledge_base_mode: Literal["legacy", "folders"] = "folders",
    ) -> None:
        if knowledge_base_mode not in {"legacy", "folders"}:
            raise ValueError("knowledge_base_mode must be 'legacy' or 'folders'")
        self._transport = Transport(base_url, username, password, timeout=timeout, verify=verify)
        self.general = General(self._transport)
        self.incidents = Incidents(self._transport)
        self.assets = Assets(self._transport)
        self.knowledge_base = KnowledgeBase(self._transport, mode=knowledge_base_mode)

    def close(self) -> None:
        """Close pooled HTTP connections. Safe to call more than once."""
        self._transport.client.close()

    @property
    def is_closed(self) -> bool:
        """Whether the underlying HTTP client has been closed."""
        return self._transport.client.is_closed

    def __enter__(self) -> "TopdeskClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
