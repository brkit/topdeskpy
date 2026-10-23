"""A focused Python client for TOPdesk's operator APIs."""

from .client import TopdeskClient
from .exceptions import APIError, PartialUpdateWarning, TopdeskError, UnexpectedResponseError

__all__ = [
    "APIError",
    "PartialUpdateWarning",
    "TopdeskClient",
    "TopdeskError",
    "UnexpectedResponseError",
]
