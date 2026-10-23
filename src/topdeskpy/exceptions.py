"""Errors raised by the TOPdesk client."""

import httpx2


class TopdeskError(Exception):
    """Base class for errors reported by TOPdesk or response decoding."""


class APIError(TopdeskError):
    """An unsuccessful HTTP response, with its original response available."""

    def __init__(self, response: httpx2.Response) -> None:
        self.response = response
        self.status_code = response.status_code
        self.method = response.request.method
        self.path = response.request.url.path
        self.body = response.text
        super().__init__(
            f"TOPdesk {self.method} {self.path}: HTTP {self.status_code}: {self.body[:1000]}"
        )


class UnexpectedResponseError(TopdeskError):
    """The server returned a response that does not match the documented shape."""


class PartialUpdateWarning(UserWarning):
    """TOPdesk accepted an asset write but ignored one or more unknown fields."""
