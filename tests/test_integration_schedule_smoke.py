"""Gated live check: schedule_manually pins a date past a relation constraint.

Skipped by default. Enable with a disposable test project:

    OPENPROJECT_SMOKE=1 OPENPROJECT_URL=... OPENPROJECT_API_KEY=... \\
    OPENPROJECT_TEST_PROJECT_ID=<id> [OPENPROJECT_TEST_TYPE_ID=1] \\
    uv run pytest tests/test_integration_schedule_smoke.py -v

It creates two work packages with a "follows" relation, then shows that a date the
relation would reject is refused WITHOUT schedule_manually and accepted WITH it.
Cleans up the work packages it creates (which also removes the relation). Requires
an instance whose scheduling enforces relation constraints (default OpenProject).
"""

import os
import re

import pytest

from src.tools.work_packages import (
    create_work_package,
    update_work_package,
    delete_work_package,
)
from src.tools.relations import create_work_package_relation, CreateRelationInput

SMOKE = os.getenv("OPENPROJECT_SMOKE") == "1"
PROJECT_ID = os.getenv("OPENPROJECT_TEST_PROJECT_ID")
TYPE_ID = os.getenv("OPENPROJECT_TEST_TYPE_ID", "1")

pytestmark = pytest.mark.skipif(
    not (SMOKE and PROJECT_ID),
    reason=(
        "live scheduling test disabled; set OPENPROJECT_SMOKE=1 + "
        "OPENPROJECT_TEST_PROJECT_ID (and real creds) to run"
    ),
)


def _wp_id(text: str) -> int:
    match = re.search(r"#(\d+)", text)
    assert match, f"could not parse work package id from: {text!r}"
    return int(match.group(1))


async def test_schedule_manually_pins_date_past_relation():
    create = create_work_package.fn
    update = update_work_package.fn
    delete = delete_work_package.fn
    relate = create_work_package_relation.fn

    pid, tid = int(PROJECT_ID), int(TYPE_ID)
    a = _wp_id(await create(project_id=pid, subject="[sched] predecessor", type_id=tid))
    b = _wp_id(await create(project_id=pid, subject="[sched] successor", type_id=tid))
    try:
        # A finishes 2026-09-30; make B follow A, so B is scheduled after A.
        await update(work_package_id=a, start_date="2026-09-01", due_date="2026-09-30")
        rel = await relate(
            input=CreateRelationInput(from_id=b, to_id=a, type="follows")
        )
        assert "❌" not in rel, rel

        # An internally-consistent (start <= due) range that lands BEFORE A finishes,
        # so only the relation constraint (not start/due) is at stake.
        early = {"start_date": "2026-09-01", "due_date": "2026-09-15"}

        # WITHOUT manual scheduling -> the relation refuses the early dates.
        auto = await update(work_package_id=b, **early)
        assert (
            "❌" in auto or "failed to update" in auto.lower()
        ), f"expected the follows relation to reject the early dates, got: {auto}"

        # WITH manual scheduling -> accepted (relation constraint bypassed, links kept).
        manual = await update(work_package_id=b, schedule_manually=True, **early)
        assert "updated successfully" in manual.lower(), manual
    finally:
        await delete(b)
        await delete(a)
