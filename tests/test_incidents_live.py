"""Additional incident and general coverage against the real test installation."""

from uuid import uuid4

import httpx2
import pytest

from topdeskpy import APIError

pytestmark = pytest.mark.live


@pytest.fixture
def owned_incidents(live_client, archive_reason):
    """Track creations immediately so failed assertions still archive our records."""
    created = []

    def create():
        tag = f"topdeskpy-live-{uuid4().hex[:16]}"
        incident = live_client.incidents.create(
            {
                "briefDescription": tag,
                "caller": {"dynamicName": tag},
                "request": f"First request {tag}",
            }
        )
        created.append(incident)
        return incident

    yield create
    for incident in created:
        identifier = incident["id"]
        if not live_client.incidents.get(identifier)["status"].endswith("Archived"):
            live_client.incidents.archive(identifier, {"id": archive_reason["id"]})
        assert live_client.incidents.get(identifier)["status"].endswith("Archived")


@pytest.mark.parametrize(
    "name",
    [
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
    ],
)
def test_incident_dropdowns(live_client, name):
    values = live_client.incidents.lookup(name, params={"pageSize": 100})
    assert values, f"Test installation needs values for {name}"
    assert all(value.get("id") and value.get("name") for value in values)


@pytest.mark.parametrize("name", ["callers", "operators", "operatorgroups"])
def test_unavailable_incident_lookup_routes(live_client, name):
    """These implemented routes are unavailable on this installation."""
    with pytest.raises(APIError) as caught:
        live_client.incidents.lookup(name, params={"page_size": 1})
    assert caught.value.status_code == 404
    assert caught.value.method == "GET"
    assert caught.value.path == f"/tas/api/incidents/{name}/lookup"


def test_incident_pages_exhaustion_and_initial_offset(live_client, live_settings, owned_incidents):
    api = live_client.incidents
    incidents = [owned_incidents(), owned_incidents()]
    query = ",".join(f"id=={incident['id']}" for incident in incidents)
    params = {"query": query, "pageSize": 2}
    expected = api.list(params=params)
    expected_ids = [incident["id"] for incident in expected]
    assert set(expected_ids) == {incident["id"] for incident in incidents}
    assert [row["id"] for row in api.iter(params={"query": query}, page_size=1)] == expected_ids
    offset_params = {"query": query, "pageStart": 1}
    assert [row["id"] for row in api.iter(params=offset_params, page_size=1)] == expected_ids[1:]
    assert offset_params == {"query": query, "pageStart": 1}
    empty_params = {"query": query, "pageStart": 2, "pageSize": 1}
    # Verify the empty result really exercises the server's 204 response.
    with httpx2.Client(
        auth=(live_settings["username"], live_settings["password"]), timeout=30
    ) as client:
        response = client.get(live_settings["base_url"] + "/incidents", params=empty_params)
    assert response.status_code == 204
    assert api.list(params=empty_params) == []
    assert list(api.iter(params=empty_params, page_size=1)) == []


def test_history_pages_requests_and_visibility(live_client, owned_incidents):
    api = live_client.incidents
    incident = owned_incidents()
    identifier, tag = incident["id"], incident["briefDescription"]
    api.update_by_number(incident["number"], {"request": f"Second request {tag}"})
    api.add_action(identifier, f"Visible action {tag}")
    api.add_action(identifier, f"Private action {tag}", invisible_for_caller=True)

    for one_page, iterator, expected_texts in (
        (api.requests, api.iter_requests, [f"First request {tag}", f"Second request {tag}"]),
        (api.actions, api.iter_actions, [f"Visible action {tag}", f"Private action {tag}"]),
    ):
        history = one_page(identifier, params={"start": 0, "page_size": 100})
        assert len(history) == 2
        assert all(any(text in row["plainText"] for row in history) for text in expected_texts)
        expected_ids = [row["id"] for row in history]
        assert [row["id"] for row in iterator(identifier, page_size=1)] == expected_ids
        first = one_page(identifier, params={"start": 0, "page_size": 1})
        second = one_page(identifier, params={"start": 1, "page_size": 1})
        assert [row["id"] for row in first + second] == expected_ids
        params = {"start": 1}
        assert [row["id"] for row in iterator(identifier, params=params, page_size=1)] == (
            expected_ids[1:]
        )
        assert params == {"start": 1}
        assert one_page(identifier, params={"start": 2, "page_size": 1}) == []
        assert list(iterator(identifier, params={"start": 2}, page_size=1)) == []


def test_optional_archive_reason_and_partial_flag(live_client, owned_incidents):
    api = live_client.incidents
    incident = owned_incidents()
    identifier = incident["id"]
    assert api.archive(identifier)["status"].endswith("Archived")
    assert api.get(identifier)["status"].endswith("Archived")
    assert not api.unarchive(identifier, unarchive_partials=False)["status"].endswith("Archived")
    assert not api.get(identifier)["status"].endswith("Archived")


def test_service_window_filters(live_client):
    api = live_client.general
    windows = api.service_windows(top=1, archived=False)
    assert len(windows) == 1
    window = windows[0]
    filtered = api.service_windows(top=1000, name=window["name"], archived=False)
    assert window["id"] in {row["id"] for row in filtered}
    assert all(window["name"].casefold() in row["name"].casefold() for row in filtered)
    absent = f"topdeskpy-absent-{uuid4().hex}"
    assert api.service_windows(top=1, name=absent, archived=True) == []
    assert api.service_windows(top=1, name=absent, archived=False) == []


def test_missing_caller_rejected(live_client):
    with pytest.raises(APIError) as caught:
        live_client.incidents.create({})
    assert caught.value.status_code == 400
    assert caught.value.method == "POST"
    assert "caller" in caught.value.body.lower()


def test_unknown_priority_rejected_without_changing_incident(live_client, owned_incidents):
    api = live_client.incidents
    incident = owned_incidents()
    with pytest.raises(APIError) as caught:
        api.update(incident["id"], {"priority": {"id": str(uuid4())}})
    assert caught.value.status_code == 400
    assert caught.value.method == "PATCH"
    assert "priority" in caught.value.body.lower()
    assert api.get(incident["id"])["briefDescription"] == incident["briefDescription"]


@pytest.mark.parametrize("identifier,status", [("invalid-identifier", 400), (str(uuid4()), 404)])
def test_invalid_incident_history_identifiers(live_client, identifier, status):
    api = live_client.incidents
    for history in (api.actions, api.requests):
        with pytest.raises(APIError) as caught:
            history(identifier)
        assert caught.value.status_code == status
        assert caught.value.method == "GET"


def test_missing_number_and_service_window(live_client):
    missing = str(uuid4())
    for operation in (
        lambda: live_client.incidents.get_by_number(f"topdeskpy-{missing}"),
        lambda: live_client.incidents.update_by_number(
            f"topdeskpy-{missing}", {"briefDescription": "Missing integration record"}
        ),
        lambda: live_client.general.service_window(missing),
    ):
        with pytest.raises(APIError) as caught:
            operation()
        assert caught.value.status_code == 404
