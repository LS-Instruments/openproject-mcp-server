"""Gated live check: create_time_entry attributes the entry via user_id.

Skipped by default. Logs time for the AUTHENTICATED user via user_id (self-
attribution is always permitted, so it needs no special permission) and verifies
the created entry is attributed to that user -- proving the user_id -> _links.user
path end to end. Cleans up the work package it creates (which removes its entry).

    OPENPROJECT_SMOKE=1 OPENPROJECT_URL=... OPENPROJECT_API_KEY=... \\
    OPENPROJECT_TEST_PROJECT_ID=<id> [OPENPROJECT_TEST_TYPE_ID=1] \\
    uv run pytest tests/test_integration_time_entry_user_smoke.py -v
"""

import os
import re

import pytest

from src.server import get_client
from src.tools.work_packages import create_work_package, delete_work_package
from src.tools.time_entries import create_time_entry, CreateTimeEntryInput

SMOKE = os.getenv("OPENPROJECT_SMOKE") == "1"
PROJECT_ID = os.getenv("OPENPROJECT_TEST_PROJECT_ID")
TYPE_ID = os.getenv("OPENPROJECT_TEST_TYPE_ID", "1")

pytestmark = pytest.mark.skipif(
    not (SMOKE and PROJECT_ID),
    reason="set OPENPROJECT_SMOKE=1 + OPENPROJECT_TEST_PROJECT_ID (and creds) to run",
)


def _id(text: str) -> int:
    match = re.search(r"#(\d+)", text)
    assert match, f"could not parse id from: {text!r}"
    return int(match.group(1))


async def test_create_time_entry_attributes_to_user():
    client = get_client()
    my_id = (await client._request("GET", "/users/me"))["id"]

    wp = _id(
        await create_work_package.fn(
            project_id=int(PROJECT_ID), subject="[te-user] wp", type_id=int(TYPE_ID)
        )
    )
    try:
        # Time-entry activities are project-scoped; read them from the WP-scoped form.
        form = await client._request(
            "POST",
            "/time_entries/form",
            {"_links": {"workPackage": {"href": f"/api/v3/work_packages/{wp}"}}},
        )
        allowed = (
            form.get("_embedded", {})
            .get("schema", {})
            .get("activity", {})
            .get("_embedded", {})
            .get("allowedValues", [])
        )
        if not allowed:
            pytest.skip("no time-entry activities available for this project")
        activity_id = allowed[0].get("id") or int(
            allowed[0]["_links"]["self"]["href"].rstrip("/").rsplit("/", 1)[-1]
        )

        res = await create_time_entry.fn(
            input=CreateTimeEntryInput(
                work_package_id=wp,
                hours=1,
                spent_on="2026-09-01",
                activity_id=activity_id,
                user_id=my_id,
            )
        )
        assert "created successfully" in res.lower(), res

        # Read the created entry back and confirm it is attributed to my_id.
        entry = await client._request("GET", f"/time_entries/{_id(res)}")
        user_href = entry.get("_links", {}).get("user", {}).get("href", "")
        assert str(my_id) in user_href, f"expected user {my_id}, got {user_href!r}"
    finally:
        await delete_work_package.fn(wp)
