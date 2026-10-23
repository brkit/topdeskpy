"""TOPdesk examples for VS Code's Python Interactive window.

Run from the repository root. Run setup first, then the cells you need, and
close the client when finished. Write cells create records and clean them up.
"""

# %% Setup: credentials and a client shared by the following cells
import os
from itertools import islice
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from dotenv import dotenv_values

from topdeskpy import APIError, TopdeskClient

config = dotenv_values(".env")


def setting(name: str, dotenv_key: str) -> str:
    value = os.environ.get(name) or config.get(name) or config.get(dotenv_key)
    if not value:
        raise ValueError(f"Set {name} in the environment or {dotenv_key} in .env")
    return value


# The supplied test installation uses the legacy knowledge explorer.
# Use "folders" for an installation that has migrated to the folder explorer.
knowledge_base_mode: Literal["legacy", "folders"] = "legacy"
client = TopdeskClient(
    setting("TOPDESK_BASE_URL", "base_url"),
    setting("TOPDESK_USERNAME", "username"),
    setting("TOPDESK_PASSWORD", "password"),
    knowledge_base_mode=knowledge_base_mode,
)

# %% Read API metadata and the first ten open incidents
print(client.general.version())
print(client.general.product_version())
for incident in islice(
    client.incidents.iter(params={"query": "closed==false", "sort": "id"}, page_size=10), 10
):
    print(incident["number"], incident["briefDescription"])

# %% Create, update, and archive an incident
reasons = client.general.archiving_reasons()
# Select the appropriate reason for your installation.
archive_reason = next(
    (reason for reason in reasons if reason["name"] == "Spam eller test data"), reasons[0]
)
incident = client.incidents.create(
    {
        "briefDescription": f"Printer example {uuid4().hex[:8]}",
        "request": "The printer does not respond.",
        "caller": {"dynamicName": "TOPdesk client example"},
    }
)
try:
    client.incidents.update(incident["id"], {"briefDescription": "Printer queue paused"})
    client.incidents.add_action(incident["id"], "Restarted the print queue.")
    print(client.incidents.get(incident["id"]))
finally:
    client.incidents.archive(incident["id"], {"id": archive_reason["id"]})

# %% Create, update, and archive a knowledge item
# Choose an enabled language and an existing parent on your installation.
language = "en"
if knowledge_base_mode == "folders":
    parents = client.knowledge_base.folders(params={"page_size": 1, "language": language})
else:
    parents = client.knowledge_base.list(
        params={"page_size": 1, "query": "archived==false", "language": language}
    )
if not parents["item"]:
    raise ValueError("Choose an existing active knowledge parent for this example")
parent_id = parents["item"][0]["id"]
item = client.knowledge_base.create(
    {
        "parent": {"id": parent_id},
        "translation": {
            "language": language,
            "content": {
                "title": f"Printer setup example {uuid4().hex[:8]}",
                "content": "Installation instructions.",
            },
        },
    }
)
try:
    client.knowledge_base.update_translation(
        item["id"], language, {"content": "Updated installation instructions."}
    )
    print(client.knowledge_base.get(item["id"], params={"language": language}))
finally:
    client.knowledge_base.archive(item["id"])

# %% Discover an asset template and its required fields
templates = client.assets.templates()["dataSet"]
for template in templates:
    if template.get("archived"):
        continue
    blank = client.assets.blank(template["id"])
    if set(blank["metadata"]["template"]["required"]) <= blank["fields"].keys():
        template_id = template["id"]
        break
else:
    raise ValueError("No active asset template exposes all its required fields")
print("Template:", template_id)
print("Required fields:", blank["metadata"]["template"]["required"])
print("Field definitions:", blank["fields"])

# %% Populate required asset dropdowns from the template's available choices
# Review or change these values before running the write cell.
asset_values: dict[str, Any] = {"name": f"Laptop example {uuid4().hex[:8]}"}
for field_name in blank["metadata"]["template"]["required"]:
    if field_name in asset_values:
        continue
    options_url = blank["fields"][field_name].get("properties", {}).get("url", "")
    options = urlsplit(options_url)
    if options.scheme or options.netloc or options.path != "assets":
        raise ValueError(f"Set asset_values[{field_name!r}] using the field definition above")
    choices = client.assets.iter(params=dict(parse_qsl(options.query)))
    choice = next((row for row in choices if not row.get("archived")), None)
    if choice is None:
        raise ValueError(f"Required field {field_name!r} has no active dropdown choices")
    asset_values[field_name] = choice["id"]
print("Asset values:", asset_values)

# %% Create, update, and delete an asset; archive it if deletion is unauthorized
payload = {"type_id": template_id, **asset_values}
missing_fields = set(blank["metadata"]["template"]["required"]) - payload.keys()
if missing_fields:
    raise ValueError(f"Add values to asset_values for required fields: {sorted(missing_fields)}")
asset_reasons = client.general.archiving_reasons()
asset_reason = next(
    (reason for reason in asset_reasons if reason["name"] == "Spam eller test data"),
    asset_reasons[0],
)
asset = client.assets.create(payload)
asset_id = asset["data"]["unid"]
try:
    card = client.assets.get(asset_id)
    client.assets.update(
        asset_id,
        {"@etag": card["data"]["@etag"], "notes": "Assigned to the service desk."},
    )
    print(client.assets.get(asset_id)["data"])
finally:
    outcome = client.assets.delete([asset_id])
    print(outcome["deleted"], outcome["unauthorized"], outcome["failed"], outcome["missing"])
    if asset_id.lower() not in {value.lower() for value in outcome["deleted"]}:
        client.assets.archive(asset_id, asset_reason["id"])

# %% Handle a missing incident
try:
    client.incidents.get(str(uuid4()))
except APIError as error:
    if error.status_code == 404:
        print("Incident not found")
    else:
        raise

# %% Close the client when finished; rerun setup to start a new session
client.close()
