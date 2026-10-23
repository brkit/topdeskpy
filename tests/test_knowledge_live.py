"""Real knowledge API pagination, validation, and explorer compatibility checks."""

from uuid import uuid4

import pytest

from topdeskpy import APIError, TopdeskClient

pytestmark = pytest.mark.live


@pytest.fixture
def knowledge_records(live_client, knowledge_languages):
    """Create isolated legacy items and always archive children before parents."""
    api = live_client.knowledge_base
    language = "da" if "da" in knowledge_languages else knowledge_languages[0]
    records = []

    def create(parent=None):
        tag = f"topdeskpy-knowledge-{uuid4().hex}"
        payload = {
            "translation": {
                "language": language,
                "content": {"title": tag, "content": f"Content {tag}"},
            },
            "externalLink": {"id": tag, "type": "98372"},
        }
        if parent is not None:
            payload["parent"] = {"id": parent["id"]}
        item = api.create(payload)
        records.append((item, tag))
        return api.get(item["id"], params={"language": language}), tag, language

    yield create

    failures = []
    for item, tag in reversed(records):
        try:
            api.archive(item["id"])
            archived = api.list(
                params={"language": language, "query": f"externalLink.id=={tag};archived==true"}
            )["item"]
            assert [row["id"] for row in archived] == [item["id"]]
        except Exception as error:
            # Continue cleanup if one archive fails so other owned items are not left active.
            failures.append(error)
    if failures:
        raise ExceptionGroup("Knowledge-item cleanup failed", failures)


def assert_api_error(caught, *, code, method, path):
    error = caught.value
    assert error.status_code == 400
    assert error.method == method
    assert error.path == f"/services/knowledge-base-v1{path}"
    assert code in {entry["errorCode"] for entry in error.response.json()["errors"]}


def test_knowledge_pagination_exhaustion(live_client, knowledge_records):
    api = live_client.knowledge_base
    root, _, language = knowledge_records()
    children = [knowledge_records(root)[0] for _ in range(3)]
    params = {
        "language": language,
        "fields": "title,parent,language",
        "query": f"parent.id=={root['id']};archived==false",
    }
    original = dict(params)
    page = api.list(params={**params, "page_size": 1000})
    expected = [row["id"] for row in page["item"]]
    assert set(expected) == {child["id"] for child in children}
    assert not page.get("next")
    first_page = api.list(params={**params, "page_size": 1})
    assert len(first_page["item"]) == 1
    assert first_page["next"]
    actual = list(api.iter(params=params, page_size=1))
    assert [row["id"] for row in actual] == expected
    assert all(row["parent"]["id"] == root["id"] for row in actual)
    assert all(row["translation"]["language"] == language for row in actual)
    assert params == original

    offset = {**params, "start": "1"}
    assert [row["id"] for row in api.iter(params=offset, page_size=1)] == expected[1:]
    assert offset["start"] == "1"
    beyond_end = {**params, "start": 3}
    assert api.list(params=beyond_end)["item"] == []
    assert list(api.iter(params=beyond_end, page_size=1)) == []
    empty = {"language": language, "query": f"parent.id=={uuid4()}"}
    assert api.list(params=empty)["item"] == []
    assert list(api.iter(params=empty, page_size=1)) == []

    # Archiving one owned child verifies that the server applies the query on every page.
    api.archive(children[1]["id"])
    assert {row["id"] for row in api.iter(params=params, page_size=1)} == {
        children[0]["id"],
        children[2]["id"],
    }


def test_knowledge_numbers_and_partial_updates(live_client, knowledge_records):
    api = live_client.knowledge_base
    item, tag, language = knowledge_records()
    identifier, number = item["id"], item["number"]
    assert " " in number, "Complete item numbers must exercise URL escaping"
    params = {"language": language, "fields": "title,content,externalLink"}
    assert api.get(number, params=params) == api.get(identifier, params=params)
    api.update(number, {"externalLink": {"id": f"{tag}-updated", "type": "98372"}})
    try:
        assert api.get(identifier, params=params)["externalLink"]["id"] == f"{tag}-updated"
        api.update_translation(number, language, {"title": f"{tag}-updated"})
        content = api.get(identifier, params=params)["translation"]["content"]
        assert content["title"] == f"{tag}-updated"
        assert content["content"] == f"Content {tag}"
        api.update(number, {"externalLink": None})
        assert api.get(identifier, params=params)["externalLink"] == {
            "id": "",
            "type": "0",
            "date": None,
        }
    finally:
        # Restore the unique cleanup filter even when a content assertion fails.
        api.update(identifier, {"externalLink": {"id": tag, "type": "98372"}})


def test_knowledge_validation_errors(live_client, knowledge_records):
    api = live_client.knowledge_base
    item, tag, language = knowledge_records()
    identifier = item["id"]
    path = f"/knowledgeItems/{identifier}"
    with pytest.raises(APIError) as caught:
        api.create({})
    assert_api_error(caught, code="translation_missing", method="POST", path="/knowledgeItems")
    with pytest.raises(APIError) as caught:
        api.update(identifier, {"parent": {"id": identifier}})
    assert_api_error(caught, code="parent_invalid", method="POST", path=path)
    with pytest.raises(APIError) as caught:
        api.create_translation(identifier, language, {"title": f"Duplicate {tag}"})
    assert_api_error(
        caught, code="translation_already_exists", method="POST", path=f"{path}/translations"
    )
    with pytest.raises(APIError) as caught:
        api.create_translation(identifier, "zz-invalid", {"title": tag})
    assert_api_error(caught, code="language_invalid", method="POST", path=f"{path}/translations")
    with pytest.raises(APIError) as caught:
        api.update_translation(identifier, "zz-invalid", {"title": tag})
    assert_api_error(
        caught, code="language_invalid", method="POST", path=f"{path}/translations/zz-invalid"
    )
    with pytest.raises(APIError) as caught:
        api.delete_translation(identifier, language)
    assert_api_error(
        caught, code="last_translation", method="DELETE", path=f"{path}/translations/{language}"
    )
    content = api.get(identifier, params={"language": language, "fields": "title"})
    assert content["translation"]["content"]["title"] == tag


def test_knowledge_archived_mutations(live_client, knowledge_records, knowledge_languages):
    api = live_client.knowledge_base
    item, tag, language = knowledge_records()
    identifier = item["id"]
    path = f"/knowledgeItems/{identifier}"
    extra_language = next(value for value in knowledge_languages if value != language)
    api.archive(item["number"])
    api.archive(identifier)  # Archiving is idempotent.
    operations = [
        (lambda: api.update(identifier, {"externalLink": None}), "POST", path),
        (
            lambda: api.update_translation(identifier, language, {"title": "Rejected"}),
            "POST",
            f"{path}/translations/{language}",
        ),
        (
            lambda: api.create_translation(identifier, extra_language, {"title": tag}),
            "POST",
            f"{path}/translations",
        ),
        (
            lambda: api.delete_translation(identifier, language),
            "DELETE",
            f"{path}/translations/{language}",
        ),
    ]
    for operation, method, error_path in operations:
        with pytest.raises(APIError) as caught:
            operation()
        assert_api_error(caught, code="item_archived", method=method, path=error_path)
    api.unarchive(item["number"])
    api.unarchive(identifier)  # Unarchiving is idempotent.
    api.update_translation(identifier, language, {"title": f"Restored {tag}"})
    assert (
        api.get(identifier, params={"language": language, "fields": "title"})["translation"][
            "content"
        ]["title"]
        == f"Restored {tag}"
    )


def test_knowledge_folder_mode_capability_errors(
    live_settings, knowledge_records, knowledge_languages
):
    """The designated legacy tenant rejects the migrated explorer's write protocol."""
    item, tag, language = knowledge_records()
    identifier = item["id"]
    path = f"/services/knowledge-base-v1/knowledgeItems/{identifier}"
    extra_language = next(value for value in knowledge_languages if value != language)
    with TopdeskClient(**live_settings) as client:
        api = client.knowledge_base  # Default mode is folders.
        assert api.migrated() == {"migrated": False}
        assert api.get(item["number"])["id"] == identifier
        with pytest.raises(APIError) as caught:
            api.folders(params={"page_size": 1, "language": language})
        assert caught.value.status_code == 404
        assert caught.value.method == "GET"
        assert caught.value.path == "/services/knowledge-base-v1/folders"
        for operation, error_path in [
            (lambda: api.update(identifier, {"externalLink": None}), path),
            (
                lambda: api.update_translation(identifier, language, {"title": "Rejected"}),
                f"{path}/translations/{language}",
            ),
        ]:
            with pytest.raises(APIError) as caught:
                operation()
            assert caught.value.status_code == 405
            assert caught.value.method == "PATCH"
            assert caught.value.path == error_path
        # Legacy POST on the per-language URL means update, not translation creation.
        with pytest.raises(APIError) as caught:
            api.create_translation(identifier, extra_language, {"title": tag})
        assert_api_error(
            caught,
            code="translation_not_found",
            method="POST",
            path=f"/knowledgeItems/{identifier}/translations/{extra_language}",
        )
        original = api.get(
            identifier, params={"language": language, "fields": "title,externalLink"}
        )
        assert original["translation"]["content"]["title"] == tag
        assert original["externalLink"]["id"] == tag
