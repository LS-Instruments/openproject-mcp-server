"""Unit coverage for update_work_package's manual-scheduling passthrough.

``schedule_manually`` maps to the OpenProject ``scheduleManually`` property, which
lets a work package keep a date its relations would otherwise push out (needed to
pin milestone dates onto committed targets). These tests mock the client / request
layer, so they are network-free.
"""

from src.client import OpenProjectClient
from src.tools import work_packages as wp


class _CaptureClient:
    def __init__(self):
        self.calls = []

    async def update_work_package(self, wp_id, data):
        self.calls.append(dict(data))
        return {"id": wp_id, "subject": "S", "_embedded": {}}


async def test_tool_passes_schedule_manually(monkeypatch):
    fake = _CaptureClient()
    monkeypatch.setattr(wp, "get_client", lambda: fake)

    result = await wp.update_work_package.fn(
        work_package_id=1, due_date="2026-08-21", schedule_manually=True
    )

    assert "updated successfully" in result.lower()
    assert fake.calls[0]["schedule_manually"] is True
    assert fake.calls[0]["dueDate"] == "2026-08-21"


async def test_tool_omits_schedule_manually_when_not_set(monkeypatch):
    fake = _CaptureClient()
    monkeypatch.setattr(wp, "get_client", lambda: fake)

    await wp.update_work_package.fn(work_package_id=1, status_id=2)

    assert "schedule_manually" not in fake.calls[0]


async def test_client_maps_schedule_manually_to_payload(monkeypatch):
    client = OpenProjectClient.__new__(OpenProjectClient)
    captured = {}

    async def fake_get_wp(wp_id):
        return {"lockVersion": 3}

    async def fake_request(method, path, payload=None):
        captured.update(method=method, path=path, payload=payload)
        return {"id": 1, "subject": "S", "_embedded": {}}

    monkeypatch.setattr(client, "get_work_package", fake_get_wp)
    monkeypatch.setattr(client, "_request", fake_request)

    await client.update_work_package(
        1, {"schedule_manually": True, "dueDate": "2026-08-21"}
    )

    assert captured["payload"]["scheduleManually"] is True
    assert captured["payload"]["dueDate"] == "2026-08-21"
    assert captured["payload"]["lockVersion"] == 3
