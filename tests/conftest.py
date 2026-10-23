"""Explicitly opted-in integration tests against the designated test installation."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
import pytest
from dotenv import dotenv_values

from topdeskpy import TopdeskClient


def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", help="Run tests that create and archive real TOPdesk records"
    )
    parser.addoption("--live-host", help="Explicit test hostname; must match base_url")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: integration test requiring real test installation credentials"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        for item in items:
            if "live" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(
                        reason="Pass --live --live-host testdesk.brkint.dk to run live tests"
                    )
                )


@pytest.fixture(scope="session")
def live_settings(pytestconfig):
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")

    def setting(name, legacy_key):
        return os.environ.get(name) or values.get(name) or values.get(legacy_key)

    base_url = setting("TOPDESK_BASE_URL", "base_url")
    username = setting("TOPDESK_USERNAME", "username")
    password = setting("TOPDESK_PASSWORD", "password")
    if not base_url or not username or not password:
        pytest.fail(
            "Live tests require TOPDESK_BASE_URL, TOPDESK_USERNAME and TOPDESK_PASSWORD "
            "in the environment or .env (legacy lowercase keys are also supported)",
            pytrace=False,
        )
    url = urlsplit(base_url)
    expected_host = pytestconfig.getoption("--live-host")
    if (
        expected_host != "testdesk.brkint.dk"
        or url.hostname != expected_host
        or url.scheme != "https"
        or url.path.rstrip("/") != "/tas/api"
    ):
        pytest.fail(
            "Live tests require --live-host testdesk.brkint.dk and matching HTTPS "
            "base_url ending /tas/api",
            pytrace=False,
        )
    return {"base_url": base_url, "username": username, "password": password}


@pytest.fixture(scope="session")
def live_client(live_settings):
    with TopdeskClient(
        **live_settings,
        knowledge_base_mode="legacy",
    ) as client:
        yield client


@pytest.fixture(scope="session")
def archive_reason(live_client):
    reasons = live_client.general.archiving_reasons()
    assert reasons, "Test installation must provide at least one archiving reason"
    return next(
        (reason for reason in reasons if reason["name"] == "Spam eller test data"), reasons[0]
    )


@pytest.fixture(scope="session")
def knowledge_languages(live_settings):
    """Read enabled languages for setup without extending the tested client scope."""
    base_url, username, password = (
        live_settings[key] for key in ("base_url", "username", "password")
    )
    with httpx2.Client(auth=(username, password), timeout=30) as client:
        response = client.get(base_url.rstrip("/") + "/knowledgeBase/languages")
        response.raise_for_status()
        languages = response.json()["results"]
        assert languages
        return [language["languageCode"] for language in languages]
