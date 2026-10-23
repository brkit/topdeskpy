"""Real API round trips. Writes affect only unique records created by each test."""

import warnings
from itertools import islice
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from topdeskpy import APIError

pytestmark = pytest.mark.live


def marker():
    return f"topdeskpy-live-{uuid4().hex[:16]}"


def test_general_metadata(live_client):
    api = live_client.general
    assert api.version()
    assert api.product_version()
    page = api.categories()
    assert isinstance(page["item"], list)
    assert page["item"], "Test installation must have incident categories"
    assert all(category.get("id") and category.get("name") for category in page["item"])
    categories = list(api.iter_categories())
    assert {row["id"] for row in page["item"]} <= {row["id"] for row in categories}
    assert api.archiving_reasons()
    assert isinstance(api.timespent_reasons(), list)
    windows = api.service_windows(top=2)
    assert windows, "Test installation needs a readable service window"
    window = api.service_window(windows[0]["id"])
    assert window["id"] == windows[0]["id"]
    assert window["name"] == windows[0]["name"]


def test_incident_lifecycle(live_client, archive_reason):
    api = live_client.incidents
    for dropdown in ("call_types", "statuses"):
        values = api.lookup(dropdown)
        assert values
        assert all(value.get("id") and value.get("name") for value in values)
    tag = marker()
    created = api.create(
        {
            "briefDescription": tag,
            "request": f"Integration request {tag}",
            "caller": {"dynamicName": tag},
        }
    )
    identifier = created["id"]
    try:
        assert api.get(identifier)["briefDescription"] == tag
        assert api.get_by_number(created["number"])["id"] == identifier
        updated_title = f"{tag} updated"
        api.update(identifier, {"briefDescription": updated_title})
        assert api.get(identifier)["briefDescription"] == updated_title
        numbered_title = f"{tag} by number"
        api.update_by_number(created["number"], {"briefDescription": numbered_title})
        assert api.get(identifier)["briefDescription"] == numbered_title
        action = f"Integration action {tag}"
        api.add_action(identifier, action, invisible_for_caller=True)
        second_action = f"Second integration action {tag}"
        api.add_action(identifier, second_action, invisible_for_caller=True)
        history = list(api.iter_actions(identifier, page_size=1))
        assert len(history) >= 2
        assert any(action in row["plainText"] for row in history)
        assert any(second_action in row["plainText"] for row in history)
        requests = list(api.iter_requests(identifier, page_size=1))
        assert any(tag in row["plainText"] for row in requests)
        listed = list(api.iter(params={"query": f"id=={identifier}"}, page_size=1))
        assert [row["id"] for row in listed] == [identifier]
        api.archive(identifier, {"id": archive_reason["id"]})
        assert api.get(identifier)["status"].endswith("Archived")
        api.unarchive(identifier)
        assert not api.get(identifier)["status"].endswith("Archived")
    finally:
        if not api.get(identifier)["status"].endswith("Archived"):
            api.archive(identifier, {"id": archive_reason["id"]})
        assert api.get(identifier)["status"].endswith("Archived")


def asset_payload(api, tag):
    """Resolve mandatory dropdown values from live template metadata."""
    templates = api.templates()["dataSet"]
    assert templates
    for template in templates:
        if template.get("archived"):
            continue
        blank = api.blank(template["id"])
        fields = blank["fields"]
        required = blank["metadata"]["template"]["required"]
        # Some migrated templates list a removed field as mandatory. Use a
        # complete template rather than guessing values for invisible fields.
        if any(field not in fields for field in required):
            continue
        payload = {"name": tag, "type_id": template["id"]}
        for field in required:
            properties = fields[field].get("properties", {})
            options_url = properties.get("url", "")
            parsed = urlsplit(options_url)
            assert parsed.path == "assets", f"Mandatory field {field} needs an explicit test value"
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            choices = api.list(params=params)["dataSet"]
            active = [choice for choice in choices if not choice.get("archived")]
            assert active, f"Mandatory field {field} has no available choices"
            payload[field] = active[0]["id"]
        return payload
    pytest.fail("No active asset template exposes all its mandatory fields")


def test_asset_lifecycle(live_client, archive_reason):
    api = live_client.assets
    tag = marker()
    created = api.create(asset_payload(api, tag))
    identifier = created["data"]["unid"]
    deleted = False
    try:
        card = api.get(identifier)
        assert card["data"]["name"] == tag
        updated = api.update(
            identifier, {"@etag": card["data"]["@etag"], "notes": f"Updated {tag}"}
        )
        assert updated["data"]["notes"] == f"Updated {tag}"
        assert api.get(identifier)["data"]["notes"] == f"Updated {tag}"
        with pytest.raises(APIError) as stale:
            api.update(identifier, {"@etag": card["data"]["@etag"], "notes": "stale write"})
        assert stale.value.status_code == 409
        assert api.get(identifier)["data"]["notes"] == f"Updated {tag}"
        listed = list(api.iter(params={"nameFragment": tag}, page_size=1))
        assert [row["id"].lower() for row in listed] == [identifier.lower()]
        api.archive(identifier, archive_reason["id"])
        assert api.get(identifier)["data"]["archived"] is True
        api.unarchive(identifier)
        assert api.get(identifier)["data"]["archived"] is False
        result = api.delete([identifier])
        expected = {identifier.lower()}
        deleted_ids = {value.lower() for value in result["deleted"]}
        unauthorized = {value.lower() for value in result["unauthorized"]}
        assert not result["failed"] and not result["missing"]
        assert (deleted_ids == expected and not unauthorized) or (
            unauthorized == expected and not deleted_ids
        ), result
        deleted = deleted_ids == expected
        if deleted:
            with pytest.raises(APIError) as error:
                api.get(identifier)
            assert error.value.status_code == 404
        else:
            warnings.warn(
                f"Permanent asset deletion is permission-limited; test asset {identifier} "
                "will be archived. Successful permanent deletion was not verified.",
                UserWarning,
                stacklevel=1,
            )
    finally:
        if not deleted:
            if not api.get(identifier)["data"]["archived"]:
                api.archive(identifier, archive_reason["id"])
            assert api.get(identifier)["data"]["archived"] is True


def test_read_pagination(live_client):
    """Compare a two-row page with two pages consumed through each iterator."""
    assets = live_client.assets
    expected_assets = assets.list(params={"pageSize": 2})["dataSet"]
    assert len(expected_assets) == 2, "Test installation needs two readable assets"
    actual_assets = list(islice(assets.iter(page_size=1), 2))
    assert [row["id"] for row in actual_assets] == [row["id"] for row in expected_assets]
    knowledge = live_client.knowledge_base
    expected_knowledge = knowledge.list(params={"page_size": 2})["item"]
    assert len(expected_knowledge) == 2, "Test installation needs two readable knowledge items"
    actual_knowledge = list(islice(knowledge.iter(page_size=1), 2))
    assert [row["id"] for row in actual_knowledge] == [row["id"] for row in expected_knowledge]


@pytest.mark.parametrize("resource", ["incidents", "assets", "knowledge_base"])
def test_missing_record_error(live_client, resource):
    with pytest.raises(APIError) as caught:
        getattr(live_client, resource).get(str(uuid4()))
    error = caught.value
    assert error.status_code == 404
    assert error.method == "GET"
    assert error.path.startswith(("/tas/api/", "/services/knowledge-base-v1/"))
    assert error.response.status_code == error.status_code


def test_invalid_incident_error(live_client):
    with pytest.raises(APIError) as caught:
        live_client.incidents.create({"status": "invalid-integration-test-status"})
    assert caught.value.status_code == 400
    assert caught.value.method == "POST"
    assert caught.value.path == "/tas/api/incidents"


def test_knowledge_item_lifecycle(live_client, knowledge_languages):
    api = live_client.knowledge_base
    tag = marker()
    migrated = api.migrated()["migrated"]
    if migrated:
        folders = api.folders()["item"]
        assert folders, "A parent folder is needed for the knowledge integration test"
        parent = {"id": folders[0]["id"]}
    else:
        existing = api.list(params={"page_size": 1, "query": "archived==false"})["item"]
        assert existing, "An active parent item is needed on the legacy knowledge explorer"
        parent = {"id": existing[0]["id"]}
    language = "da"
    created = api.create(
        {
            "parent": parent,
            "translation": {
                "language": language,
                "content": {"title": tag, "content": f"Integration content {tag}"},
            },
        }
    )
    identifier = created["id"]
    archived = False
    extra_language = next((value for value in knowledge_languages if value != language), None)
    translation_created = False

    def listed_in_state(state):
        query = f"parent.id=={parent['id']};archived=={str(state).lower()}"
        return identifier in {row["id"] for row in api.iter(params={"query": query})}

    try:
        params = {"fields": "title,content,language,visibility", "language": language}
        item = api.get(identifier, params=params)
        assert item["translation"]["content"]["title"] == tag
        assert api.get(item["number"], params=params)["id"] == identifier
        api.update(identifier, {"externalLink": {"id": tag, "type": "98372"}})
        metadata = api.get(identifier, params={"fields": "externalLink"})
        assert metadata["externalLink"]["id"] == tag
        assert metadata["externalLink"]["type"] == "98372"
        api.update_translation(identifier, language, {"content": f"Updated content {tag}"})
        assert (
            api.get(identifier, params=params)["translation"]["content"]["content"]
            == f"Updated content {tag}"
        )
        if extra_language:
            api.create_translation(identifier, extra_language, {"title": f"English {tag}"})
            translation_created = True
            translated = api.get(
                identifier, params={"language": extra_language, "fields": "title,language"}
            )
            assert translated["translation"]["language"] == extra_language
            assert translated["translation"]["content"]["title"] == f"English {tag}"
            api.delete_translation(identifier, extra_language)
            translation_created = False
            translations = api.get(identifier, params={"fields": "availableTranslations"})
            assert language in translations["availableTranslations"]
            # This legacy installation retains a blank language entry after
            # deletion. Verify removal of our content and preservation of the
            # original translation rather than trusting the language index.
            removed = api.get(
                identifier, params={"language": extra_language, "fields": "title,content"}
            )
            assert not removed["translation"]["content"].get("title")
            assert not removed["translation"]["content"].get("content")
            assert api.get(identifier, params=params)["translation"]["content"]["title"] == tag
        else:
            warnings.warn(
                "The test installation enables only one knowledge language; additional "
                "translation creation and deletion cannot be verified.",
                UserWarning,
                stacklevel=1,
            )
        api.archive(identifier)
        archived = True
        assert listed_in_state(True)
        assert not listed_in_state(False)
        api.unarchive(identifier)
        archived = False
        assert listed_in_state(False)
        assert not listed_in_state(True)
    finally:
        if translation_created:
            api.delete_translation(identifier, extra_language)
        if not archived:
            api.archive(identifier)
        assert listed_in_state(True)
