"""Transport contracts checked with actual TOPdesk responses and live sessions."""

import ssl
from typing import Any
from uuid import uuid4

import httpx2
import pytest
import truststore

from topdeskpy import APIError, TopdeskClient, UnexpectedResponseError
from topdeskpy.knowledge_base import KnowledgeBase

pytestmark = pytest.mark.live


def test_origin_urls_timeout_tls_and_connection_cleanup(live_settings):
    settings = dict(live_settings)
    settings["base_url"] = settings["base_url"].removesuffix("/tas/api") + "/"
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client = TopdeskClient(
        **settings,
        timeout=httpx2.Timeout(30, connect=10),
        verify=context,
    )
    assert not client.is_closed
    with pytest.raises(APIError) as missing, client:
        assert client.general.version()["version"]
        client.incidents.get(str(uuid4()))
    assert missing.value.status_code == 404
    assert client.is_closed
    client.close()
    assert client.is_closed


def test_absolute_paths_and_cross_origin_rejection(live_client):
    transport = live_client._transport
    expected = live_client.general.version()
    # Absolute URLs are used by server-provided pagination links. Root paths
    # are used by the Knowledge Base service on the same installation.
    absolute = transport.object("GET", transport.base_url + "version")
    root_path = transport.object("GET", "/tas/api/version")
    assert absolute == root_path == expected
    for path in (
        "https://example.invalid/tas/api/version",
        "//example.invalid/tas/api/version",
        "/unsupported-api/version",
    ):
        with pytest.raises(ValueError):
            transport.request("GET", path)
    assert live_client.general.version() == expected


def test_real_responses_enforce_object_and_collection_contracts(live_client):
    transport = live_client._transport
    assert live_client.general.version()["version"]
    assert live_client.general.archiving_reasons()
    # These endpoints provide real JSON objects and arrays, respectively.
    # Requesting the wrong contract must fail rather than silently returning
    # an incompatible type. No response bodies or HTTP responses are invented.
    with pytest.raises(UnexpectedResponseError, match="JSON object array"):
        transport.objects("GET", "version")
    with pytest.raises(UnexpectedResponseError, match="JSON object from"):
        transport.object("GET", "archiving-reasons")
    with pytest.raises(UnexpectedResponseError, match="JSON object array"):
        list(transport.iter_offset("version", page_size=1))
    version = transport.object("GET", "version")
    with pytest.raises(UnexpectedResponseError, match="object array"):
        transport.collection(version, "version", "version")
    assert live_client.general.version() == version


def test_server_rejects_unknown_credentials(live_settings):
    # Use a nonexistent operator rather than failing authentication on a real
    # account that might have a lockout policy.
    settings: dict[str, Any] = {**live_settings, "username": f"topdeskpy-missing-{uuid4().hex}"}
    with TopdeskClient(**settings) as client, pytest.raises(APIError) as denied:
        client.general.version()
    assert denied.value.status_code == 401
    assert denied.value.method == "GET"
    assert denied.value.path == "/tas/api/version"


def test_invalid_connection_settings_preserve_existing_live_session(live_settings, live_client):
    expected = live_client.general.version()
    origin = live_client._transport.origin
    for changes in (
        {"base_url": "testdesk.brkint.dk/tas/api"},
        {"base_url": f"{origin}/tas/api?unexpected=true"},
        {"base_url": f"{origin}/tas/api#fragment"},
        {"base_url": "https://embedded:credentials@testdesk.brkint.dk/tas/api"},
        {"base_url": f"{origin}/unsupported-api"},
        {"username": ""},
        {"password": ""},
        {"knowledge_base_mode": "unknown"},
    ):
        invalid_settings: dict[str, Any] = {**live_settings, **changes}
        with pytest.raises(ValueError):
            TopdeskClient(**invalid_settings)
    invalid_mode: dict[str, Any] = {"mode": "unknown"}
    with pytest.raises(ValueError):
        KnowledgeBase(live_client._transport, **invalid_mode)
    assert live_client.general.version() == expected


def test_invalid_pagination_is_rejected_and_valid_requests_still_work(live_client):
    # Invalid limits must fail locally. The surrounding reads verify that the
    # same live client still accepts valid API requests after those failures.
    before = live_client.incidents.list(params={"pageSize": 1, "sort": "id"})
    assert before
    for size in (0, -1, 10001):
        with pytest.raises(ValueError):
            list(live_client.incidents.iter(page_size=size))
    for size in (0, 1001):
        with pytest.raises(ValueError):
            list(live_client.assets.iter(page_size=size))
        with pytest.raises(ValueError):
            list(live_client.knowledge_base.iter(page_size=size))
    for size in (0, 101):
        with pytest.raises(ValueError):
            list(live_client.incidents.iter_actions(before[0]["id"], page_size=size))
        with pytest.raises(ValueError):
            list(live_client.incidents.iter_requests(before[0]["id"], page_size=size))
    for size in (0, 10001):
        with pytest.raises(ValueError):
            live_client.general.service_windows(top=size)
    for key in ("lastSeenName", "lastSeenOrderbyValue"):
        with pytest.raises(ValueError, match="Seek pagination"):
            list(live_client.assets.iter(params={key: "example"}))
    with pytest.raises(ValueError):
        list(live_client._transport.iter_offset("incidents", page_size=0))
    after = live_client.incidents.list(params={"pageSize": 1, "sort": "id"})
    assert after[0]["id"] == before[0]["id"]
    assert live_client.assets.list(params={"pageSize": 1})["dataSet"]
    assert live_client.knowledge_base.list(params={"page_size": 1})["item"]


def test_invalid_identifiers_and_lookup_leave_live_client_usable(live_client):
    incident = live_client.incidents.list(params={"pageSize": 1})[0]
    for identifier in ("", ".", ".."):
        with pytest.raises(ValueError):
            live_client.incidents.get(identifier)
    with pytest.raises(ValueError, match="Unsupported incident lookup"):
        live_client.incidents.lookup("not_a_lookup")
    assert live_client.incidents.get(incident["id"])["id"] == incident["id"]
    assert live_client.incidents.lookup("statuses")
