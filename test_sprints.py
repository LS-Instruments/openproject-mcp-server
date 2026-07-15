#!/usr/bin/env python3
"""
Unit tests for the sprint & backlog tools (network-free).

Covers status parsing (the API models status via _links.status), sprint
formatting, and the work-package filter construction (sprint "=" for a sprint,
sprint "!*" for the backlog). The HTTP client is mocked.

    python test_sprints.py
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPENPROJECT_URL", "http://localhost")
os.environ.setdefault("OPENPROJECT_API_KEY", "test-key")

from src.tools.sprints import (  # noqa: E402
    list_sprints,
    list_sprint_work_packages,
    list_backlog_work_packages,
    _sprint_status,
    _format_sprint,
    _norm_status,
)


def _sprint(sid, name, status_title, start="2026-09-01", finish="2026-09-14"):
    return {
        "id": sid,
        "name": name,
        "startDate": start,
        "finishDate": finish,
        "_links": {
            "status": {"title": status_title},
            "definingWorkspace": {"title": "Demo Project"},
        },
    }


def test_status_parsing():
    print("\n[1] status is read from _links.status and normalised")
    try:
        assert _norm_status("In planning") == "in_planning"
        assert _sprint_status(_sprint(1, "S", "Active")) == "active"
        assert _sprint_status({"status": "completed"}) == "completed"
        assert _sprint_status({}) == "unknown"
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def test_format_sprint():
    print("\n[2] _format_sprint shows icon, name, status, dates, project")
    try:
        out = _format_sprint(_sprint(7, "Sprint 7", "active"))
        assert "Sprint 7" in out and "(ID: 7)" in out
        assert "🟢" in out and "active" in out
        assert "Demo Project" in out
        assert "2026-09-01 → 2026-09-14" in out
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


async def _capture_wp_filters(coro_factory):
    captured = {}

    async def fake_get_wps(project_id=None, filters=None, **kw):
        captured["filters"] = json.loads(filters) if filters else []
        captured["project_id"] = project_id
        return {"_embedded": {"elements": []}, "total": 0}

    with patch("src.tools.sprints.get_client") as gc:
        client = AsyncMock()
        client.get_work_packages = AsyncMock(side_effect=fake_get_wps)
        gc.return_value = client
        await coro_factory()
    return captured


def _by_key(filters):
    return {list(f.keys())[0]: list(f.values())[0] for f in filters}


def test_sprint_wp_filter():
    print("\n[3] list_sprint_work_packages filters by sprint = <id>")
    try:
        cap = asyncio.run(
            _capture_wp_filters(lambda: list_sprint_work_packages.fn(sprint_id=12))
        )
        bk = _by_key(cap["filters"])
        assert bk.get("sprint") == {"operator": "=", "values": ["12"]}, bk
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def test_backlog_filter():
    print("\n[4] list_backlog_work_packages filters by sprint !* (+ type/priority)")
    try:
        cap = asyncio.run(
            _capture_wp_filters(
                lambda: list_backlog_work_packages.fn(
                    project_id=5, type_ids="1,2", priority_ids="3"
                )
            )
        )
        bk = _by_key(cap["filters"])
        assert bk.get("sprint") == {"operator": "!*", "values": []}, bk
        assert bk.get("type") == {"operator": "=", "values": ["1", "2"]}, bk
        assert bk.get("priority") == {"operator": "=", "values": ["3"]}, bk
        assert cap["project_id"] == 5
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def test_list_sprints_status_filter():
    print("\n[5] list_sprints filters by status client-side")
    try:

        async def run():
            async def fake_get_sprints(project_id=None, offset=0, page_size=25):
                return {
                    "_embedded": {
                        "elements": [
                            _sprint(1, "Planning one", "in_planning"),
                            _sprint(2, "Active one", "active"),
                        ]
                    },
                    "total": 2,
                }

            with patch("src.tools.sprints.get_client") as gc:
                client = AsyncMock()
                client.get_sprints = AsyncMock(side_effect=fake_get_sprints)
                gc.return_value = client
                return await list_sprints.fn(status="active")

        out = asyncio.run(run())
        assert "Active one" in out and "Planning one" not in out, out
        # invalid status is rejected
        bad = asyncio.run(list_sprints.fn(status="bogus"))
        assert "Invalid status" in bad, bad
        print("OK PASSED")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def run_all_tests():
    print("=" * 70)
    print("Sprint & backlog tools - UNIT TEST SUITE")
    print("=" * 70)
    results = [
        test_status_parsing(),
        test_format_sprint(),
        test_sprint_wp_filter(),
        test_backlog_filter(),
        test_list_sprints_status_filter(),
    ]
    passed = sum(1 for r in results if r)
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
