#!/usr/bin/env python3
"""
Unit tests for list_time_entries - regression tests for two bugs.

Bug A: the work-package filter used a non-existent identifier, so
       list_time_entries(work_package_id=...) returned
       400 InvalidQuery "Work package filter does not exist."
Bug B: the API returns a time entry's ``hours`` as an ISO-8601 duration
       string (e.g. "PT4H"), so summing them raised
       TypeError: unsupported operand type(s) for +=: 'int' and 'str'.

Network-free: the OpenProject client is mocked. Run as a plain script:

    python test_list_time_entries.py
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importing the server module requires these; dummy values are fine since the
# HTTP client is mocked in every test below (no real requests are made).
os.environ.setdefault("OPENPROJECT_URL", "http://localhost")
os.environ.setdefault("OPENPROJECT_API_KEY", "test-key")

from src.tools.time_entries import list_time_entries, _hours_to_float  # noqa: E402


def test_duration_parsing():
    """_hours_to_float turns ISO-8601 durations into a number of hours."""
    print("\n" + "=" * 70)
    print("Test 1: _hours_to_float duration parsing")
    print("=" * 70)

    cases = [
        ("PT4H", 4.0),
        ("PT1H30M", 1.5),
        ("PT45M", 0.75),
        ("PT8H15M", 8.25),
        ("P1DT2H", 26.0),
        ("", 0.0),
        ("garbage", 0.0),
        (None, 0.0),
        (2.5, 2.5),
        (3, 3.0),
    ]
    for value, expected in cases:
        got = _hours_to_float(value)
        if got != expected:
            print(
                f"  ❌ FAILED: _hours_to_float({value!r}) = {got}, expected {expected}"
            )
            return False
        print(f"  ✅ _hours_to_float({value!r}) = {got}")
    return True


async def _run_list(**kwargs):
    """Call list_time_entries with a mocked client.

    Returns (result_text, filters_json_sent_to_client).
    """
    captured = {}

    async def fake_get_time_entries(filters=None):
        captured["filters"] = filters
        return {
            "_embedded": {
                "elements": [
                    {"id": 1, "hours": "PT4H", "spentOn": "2026-09-01"},
                    {"id": 2, "hours": "PT1H30M", "spentOn": "2026-09-02"},
                ]
            }
        }

    with patch("src.tools.time_entries.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_time_entries = AsyncMock(side_effect=fake_get_time_entries)
        mock_get_client.return_value = mock_client
        result = await list_time_entries.fn(**kwargs)
    return result, captured.get("filters")


def test_hours_sum_no_crash():
    """Bug B: string durations are parsed, summed, and rendered numerically."""
    print("\n" + "=" * 70)
    print("Test 2: hours are parsed and summed (no TypeError, no raw PT4H)")
    print("=" * 70)

    result, _ = asyncio.run(_run_list())

    checks = [
        ("PT4H" not in result, "raw 'PT4H' must not appear in output"),
        ("Hours: 4.0" in result, "PT4H entry renders as 4.0"),
        ("Hours: 1.5" in result, "PT1H30M entry renders as 1.5"),
        ("**Total Hours**: 5.5" in result, "total is the numeric sum 4.0 + 1.5"),
    ]
    for ok, label in checks:
        if not ok:
            print(f"  ❌ FAILED: {label}\n--- output ---\n{result}")
            return False
        print(f"  ✅ {label}")
    return True


def test_work_package_filter_identifier():
    """Bug A: work_package_id maps to the entity filter, not 'work_package'."""
    print("\n" + "=" * 70)
    print("Test 3: work-package filter uses entity_type + entity_id")
    print("=" * 70)

    _, filters = asyncio.run(_run_list(work_package_id=42))
    parsed = json.loads(filters)
    by_key = {list(f.keys())[0]: list(f.values())[0] for f in parsed}

    if "work_package" in by_key:
        print("  ❌ FAILED: the invalid 'work_package' filter is still used")
        return False
    print("  ✅ the invalid 'work_package' filter is gone")

    if by_key.get("entity_type", {}).get("values") != ["WorkPackage"]:
        print(
            f"  ❌ FAILED: entity_type filter missing/wrong: {by_key.get('entity_type')}"
        )
        return False
    print("  ✅ entity_type = WorkPackage")

    if by_key.get("entity_id", {}).get("values") != ["42"]:
        print(f"  ❌ FAILED: entity_id filter missing/wrong: {by_key.get('entity_id')}")
        return False
    print("  ✅ entity_id = 42")
    return True


def test_user_and_date_filters():
    """user_id maps to 'user_id'; from/to map to spent_on with the <>d operator."""
    print("\n" + "=" * 70)
    print("Test 4: user_id and spent_on date-range filters")
    print("=" * 70)

    _, filters = asyncio.run(
        _run_list(user_id=7, from_date="2026-01-01", to_date="2026-12-31")
    )
    parsed = json.loads(filters)
    by_key = {list(f.keys())[0]: list(f.values())[0] for f in parsed}

    if by_key.get("user_id", {}).get("values") != ["7"]:
        print(f"  ❌ FAILED: user_id filter missing/wrong: {by_key.get('user_id')}")
        return False
    print("  ✅ user_id = 7")

    spent_on = by_key.get("spent_on", {})
    if spent_on.get("operator") != "<>d":
        print(f"  ❌ FAILED: spent_on op != '<>d': {spent_on.get('operator')}")
        return False
    if spent_on.get("values") != ["2026-01-01", "2026-12-31"]:
        print(f"  ❌ FAILED: spent_on values wrong: {spent_on.get('values')}")
        return False
    print("  ✅ spent_on uses <>d with [from, to]")

    # from-only leaves the upper bound open
    _, filters = asyncio.run(_run_list(from_date="2026-01-01"))
    parsed = json.loads(filters)
    spent_on = parsed[0]["spent_on"]
    if spent_on.get("values") != ["2026-01-01", ""]:
        print(f"  ❌ FAILED: from-only not left open: {spent_on.get('values')}")
        return False
    print("  ✅ from-only date leaves the upper bound open")
    return True


def run_all_tests():
    print("=" * 70)
    print("list_time_entries - UNIT TEST SUITE")
    print("=" * 70)

    results = [
        ("Duration parsing", test_duration_parsing()),
        ("Hours sum (no crash)", test_hours_sum_no_crash()),
        ("Work-package filter", test_work_package_filter_identifier()),
        ("User/date filters", test_user_and_date_filters()),
    ]

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, ok in results:
        print(f"{name}: {'✅ PASSED' if ok else '❌ FAILED'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    return all(ok for _, ok in results)


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
