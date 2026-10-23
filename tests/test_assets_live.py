"""Asset contracts exercised against real, uniquely named test records."""

from uuid import uuid4

import pytest
from test_live import asset_payload

from topdeskpy import APIError, PartialUpdateWarning

pytestmark = pytest.mark.live


@pytest.fixture
def asset_requests(live_client):
    """Observe real HTTP responses without replacing transport behavior."""
    responses = []
    hooks = live_client._transport.client.event_hooks["response"]
    hooks.append(responses.append)
    try:
        yield responses
    finally:
        hooks.remove(responses.append)


@pytest.fixture
def owned_assets(live_client, archive_reason):
    api = live_client.assets
    tag = f"topdeskpy-assets-{uuid4().hex[:16]}"
    payload = asset_payload(api, tag)
    records = []

    def create(suffix, **fields):
        # Register a successful create even when it emits a partial-save warning.
        record = api.create({**payload, "name": f"{tag}-{suffix}", **fields})
        records.append(record["data"]["unid"])
        return record

    yield api, payload, tag, create
    for identifier in records:
        card = api.get(identifier)["data"]
        if not card["archived"]:
            api.archive(identifier, archive_reason["id"])
        assert api.get(identifier)["data"]["archived"] is True


def test_asset_partial_saves_and_validation(owned_assets, asset_requests):
    api, payload, tag, create = owned_assets
    unknown = "topdeskpy-unknown-field-" + uuid4().hex
    with pytest.warns(PartialUpdateWarning, match="ignored"):
        created = create("partial", **{unknown: "ignored", "notes": tag})
    assert asset_requests[-1].status_code == 202
    identifier = created["data"]["unid"]
    before = api.get(identifier)["data"]
    assert before["name"] == f"{tag}-partial"
    assert before["notes"] == tag
    assert unknown not in before

    with pytest.warns(PartialUpdateWarning, match="ignored"):
        updated = api.update(
            identifier,
            {"@etag": before["@etag"], "notes": f"{tag}-updated", unknown: "ignored"},
        )
    assert asset_requests[-1].status_code == 202
    after = api.get(identifier)["data"]
    assert updated["data"]["notes"] == after["notes"] == f"{tag}-updated"
    assert unknown not in after
    # Unknown fields must not silently change any unrelated persisted value.
    ignored_metadata = {"@etag", "modificationDate", "notes"}
    assert {k: v for k, v in before.items() if k not in ignored_metadata} == {
        k: v for k, v in after.items() if k not in ignored_metadata
    }

    with pytest.raises(APIError) as stale:
        api.update(identifier, {"@etag": before["@etag"], "notes": "stale write"})
    assert stale.value.status_code == 409
    assert api.get(identifier)["data"]["notes"] == f"{tag}-updated"

    with pytest.raises(APIError) as invalid_create:
        api.create({"name": f"{tag}-invalid"})
    assert invalid_create.value.status_code == 400
    required = api.blank(payload["type_id"])["metadata"]["template"]["required"]
    assert required, "Selected test template must expose a required field"
    for field in required:
        with pytest.raises(APIError) as invalid_update:
            api.update(identifier, {"@etag": after["@etag"], field: None})
        assert invalid_update.value.status_code == 400
    assert api.get(identifier)["data"] == after


def test_asset_pagination_filters_and_archive(owned_assets, archive_reason, asset_requests):
    api, payload, tag, create = owned_assets
    cards = [create(str(index))["data"] for index in range(3)]
    expected = [card["unid"].lower() for card in cards]
    params = {"nameFragment": tag, "$orderby": "name asc", "fetchCount": True}
    first = api.list(params={**params, "pageSize": 1})
    assert asset_requests[-1].status_code == 206
    assert len(first["dataSet"]) == 1
    asset_requests.clear()
    rows = list(api.iter(params=params, page_size=1))
    assert [row["id"].lower() for row in rows] == expected
    assert [response.status_code for response in asset_requests] == [206, 206, 200]
    assert params == {"nameFragment": tag, "$orderby": "name asc", "fetchCount": True}
    assert [
        row["id"].lower() for row in api.iter(params={**params, "pageStart": 1}, page_size=1)
    ] == expected[1:]
    assert list(api.iter(params={**params, "pageStart": 3}, page_size=1)) == []
    seek = {"lastSeenName": rows[0]["text"], "lastSeenOrderbyValue": rows[0]["text"]}
    seek_rows = api.list(params={**params, **seek, "pageSize": 3})["dataSet"]
    assert [row["id"].lower() for row in seek_rows] == expected[1:]

    filtered = api.list(
        params={
            "nameFragment": tag,
            "templateId": payload["type_id"],
            "fields": "name,notes,@type",
            "$filter": f"id eq '{cards[1]['unid']}'",
        }
    )
    assert [row["unid"].lower() for row in filtered["dataSet"]] == [expected[1]]
    assert filtered["dataSet"][0]["name"] == cards[1]["name"]
    assert {column["fieldName"] for column in filtered["columns"]} == {"name", "notes", "@type"}
    identifier = cards[1]["unid"]
    api.archive(identifier, archive_reason["id"])
    assert api.get(identifier)["data"]["archived"] is True
    assert [
        row["id"].lower() for row in api.iter(params={**params, "archived": True}, page_size=1)
    ] == [expected[1]]
    assert [
        row["id"].lower() for row in api.iter(params={**params, "archived": False}, page_size=1)
    ] == [expected[0], expected[2]]
    api.unarchive(identifier)
    assert api.get(identifier)["data"]["archived"] is False
    assert list(api.iter(params={**params, "archived": True})) == []


def test_asset_bulk_delete_permission_and_missing(owned_assets):
    api, _, _, create = owned_assets
    identifiers = [create(str(index))["data"]["unid"] for index in range(2)]
    missing = str(uuid4())
    result = api.delete([*identifiers, missing])
    assert not result["deleted"] and not result["failed"]
    assert {value.lower() for value in result["unauthorized"]} == {
        value.lower() for value in identifiers
    }
    assert {value.lower() for value in result["missing"]} == {missing}
    assert all(api.get(identifier)["data"]["archived"] is False for identifier in identifiers)


@pytest.mark.parametrize("identifier", ["not-a-uuid", pytest.param(None, id="missing-uuid")])
def test_asset_invalid_and_missing_uuid(live_client, identifier):
    identifier = identifier or str(uuid4())
    with pytest.raises(APIError) as error:
        live_client.assets.get(identifier)
    assert error.value.status_code == 404
    assert error.value.method == "GET"
    assert error.value.path == f"/tas/api/assetmgmt/assets/{identifier}"
