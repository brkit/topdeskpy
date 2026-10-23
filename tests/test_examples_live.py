"""Execute the actual example file against the configured test installation."""

from pathlib import Path

import pytest

from topdeskpy import APIError

pytestmark = pytest.mark.live


def test_all_example_cells(live_settings, live_client, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    for name in ("base_url", "username", "password"):
        monkeypatch.setenv(f"TOPDESK_{name.upper()}", live_settings[name])

    path = root / "examples.py"
    namespace = {}
    try:
        # The cell markers are comments: executing the file runs the same code
        # as VS Code's Run All, including its setup and cleanup cells.
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        assert namespace["client"].is_closed

        incident = live_client.incidents.get(namespace["incident"]["id"])
        assert incident["briefDescription"] == "Printer queue paused"
        assert incident["status"].endswith("Archived")

        item = live_client.knowledge_base.get(
            namespace["item"]["id"],
            params={"language": namespace["language"], "fields": "title,content"},
        )
        assert item["translation"]["content"]["content"] == "Updated installation instructions."
        archived = live_client.knowledge_base.iter(
            params={"query": f"parent.id=={namespace['parent_id']};archived==true"}
        )
        assert item["id"] in {row["id"] for row in archived}

        required = namespace["blank"]["metadata"]["template"]["required"]
        assert all(namespace["payload"].get(field) for field in required)
        asset_id = namespace["asset_id"]
        if asset_id.lower() in {value.lower() for value in namespace["outcome"]["deleted"]}:
            with pytest.raises(APIError) as missing:
                live_client.assets.get(asset_id)
            assert missing.value.status_code == 404
        else:
            asset = live_client.assets.get(asset_id)
            assert asset["data"]["archived"] is True
            assert asset["data"]["notes"] == "Assigned to the service desk."
    finally:
        if "client" in namespace:
            namespace["client"].close()
