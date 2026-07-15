#!/usr/bin/env python3
"""
Unit tests for work-package custom-field support (create/update).

Bug: create_work_package / update_work_package could not send custom fields, so
customField* values never reached the OpenProject payload. These tests verify the
client maps custom fields correctly (text/number directly, list/user/version-type
under _links) and that the tools forward a custom_fields mapping into the request.

Network-free: the HTTP client is mocked. Run as a plain script:

    python test_custom_fields.py
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importing the server module requires these; dummy values are fine (client mocked).
os.environ.setdefault("OPENPROJECT_URL", "http://localhost")
os.environ.setdefault("OPENPROJECT_API_KEY", "test-key")

from src.client import OpenProjectClient  # noqa: E402
from src.tools.work_packages import (  # noqa: E402
    CreateWorkPackageInput,
    UpdateWorkPackageInput,
    create_work_package,
    update_work_package,
)

TEXT_CF = "customField1"
LIST_CF = "customField2"
LIST_HREF = "/api/v3/custom_options/12"


def _client_create_payload(data):
    """Run client.create_work_package(data) with a mocked _request; return payload."""
    client = OpenProjectClient("http://x", "k")
    captured = {}

    async def fake_request(method, endpoint, body=None):
        if endpoint.endswith("/form"):
            return {"payload": {"_links": {}}, "lockVersion": 3}
        captured["payload"] = body
        return {"id": 99}

    with patch.object(OpenProjectClient, "_request", side_effect=fake_request):
        asyncio.run(client.create_work_package(data))
    return captured.get("payload", {})


def _client_update_payload(data):
    """Run client.update_work_package with a mocked _request; return payload."""
    client = OpenProjectClient("http://x", "k")
    captured = {}

    async def fake_request(method, endpoint, body=None):
        if method == "GET":
            return {"lockVersion": 5}
        captured["payload"] = body
        return {"id": 7}

    with patch.object(OpenProjectClient, "_request", side_effect=fake_request):
        asyncio.run(client.update_work_package(7, data))
    return captured.get("payload", {})


def test_model_accepts_custom_fields():
    print("\n[1] Models accept optional custom_fields")
    try:
        c = CreateWorkPackageInput(
            project_id=1,
            subject="x",
            type_id=1,
            custom_fields={TEXT_CF: "ACME", LIST_CF: {"href": LIST_HREF}},
        )
        assert c.custom_fields[TEXT_CF] == "ACME"
        u = UpdateWorkPackageInput(work_package_id=7)
        assert u.custom_fields is None
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def test_client_maps_custom_fields():
    print("\n[2] Client maps text directly and href under _links (create + update)")
    try:
        data = {
            "project": 1,
            "subject": "x",
            "type": 1,
            TEXT_CF: "ACME",
            LIST_CF: {"href": LIST_HREF},
        }
        p = _client_create_payload(data)
        assert p.get(TEXT_CF) == "ACME", f"text cf not direct: {p.get(TEXT_CF)}"
        assert p.get("_links", {}).get(LIST_CF) == {"href": LIST_HREF}, p.get("_links")

        pu = _client_update_payload({TEXT_CF: "ACME", LIST_CF: {"href": LIST_HREF}})
        assert pu.get(TEXT_CF) == "ACME"
        assert pu.get("_links", {}).get(LIST_CF) == {"href": LIST_HREF}
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def test_no_custom_fields_is_clean():
    print("\n[3] Omitting custom fields adds no customField keys")
    try:
        p = _client_create_payload({"project": 1, "subject": "x", "type": 1})
        assert not any(str(k).startswith("customField") for k in p), p
        assert not any(
            str(k).startswith("customField") for k in p.get("_links", {})
        ), p.get("_links")
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def test_tool_forwards_custom_fields():
    print("\n[4] Tools forward custom_fields into the client data dict")
    try:
        captured = {}

        async def fake_create(data):
            captured["create"] = data
            return {"id": 1, "subject": "x"}

        async def fake_update(wp_id, data):
            captured["update"] = data
            return {"id": wp_id}

        with patch("src.tools.work_packages.get_client") as gc:
            client = AsyncMock()
            client.create_work_package = AsyncMock(side_effect=fake_create)
            client.update_work_package = AsyncMock(side_effect=fake_update)
            gc.return_value = client

            asyncio.run(
                create_work_package.fn(
                    CreateWorkPackageInput(
                        project_id=1,
                        subject="x",
                        type_id=1,
                        custom_fields={TEXT_CF: "ACME"},
                    )
                )
            )
            asyncio.run(
                update_work_package.fn(
                    UpdateWorkPackageInput(
                        work_package_id=7, custom_fields={LIST_CF: {"href": LIST_HREF}}
                    )
                )
            )
        assert captured["create"].get(TEXT_CF) == "ACME", captured["create"]
        assert captured["update"].get(LIST_CF) == {"href": LIST_HREF}, captured[
            "update"
        ]
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def run_all_tests():
    print("=" * 70)
    print("Work-package custom fields - UNIT TEST SUITE")
    print("=" * 70)
    results = [
        test_model_accepts_custom_fields(),
        test_client_maps_custom_fields(),
        test_no_custom_fields_is_clean(),
        test_tool_forwards_custom_fields(),
    ]
    passed = sum(1 for r in results if r)
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
