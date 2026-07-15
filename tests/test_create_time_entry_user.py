"""Unit coverage for create_time_entry user attribution (log time for another user).

``user_id`` maps to the OpenProject time-entry ``_links.user``, so an entry can be
attributed to a project member other than the authenticated API user. When omitted,
OpenProject defaults it to the authenticated user. These mock the client / request
layer, so they are network-free.
"""

from src.client import OpenProjectClient
from src.tools import time_entries as te


class _CaptureClient:
    def __init__(self):
        self.calls = []

    async def create_time_entry(self, data):
        self.calls.append(dict(data))
        return {"id": 1, "hours": "PT2H", "spentOn": "2026-09-01", "_embedded": {}}


async def test_tool_passes_user_id(monkeypatch):
    fake = _CaptureClient()
    monkeypatch.setattr(te, "get_client", lambda: fake)

    await te.create_time_entry.fn(
        input=te.CreateTimeEntryInput(
            work_package_id=1,
            hours=2,
            spent_on="2026-09-01",
            activity_id=3,
            user_id=58,
        )
    )

    assert fake.calls[0]["user_id"] == 58


async def test_tool_omits_user_id_when_not_set(monkeypatch):
    fake = _CaptureClient()
    monkeypatch.setattr(te, "get_client", lambda: fake)

    await te.create_time_entry.fn(
        input=te.CreateTimeEntryInput(
            work_package_id=1, hours=2, spent_on="2026-09-01", activity_id=3
        )
    )

    assert "user_id" not in fake.calls[0]


async def test_client_sets_user_link(monkeypatch):
    client = OpenProjectClient.__new__(OpenProjectClient)
    captured = {}

    async def fake_request(method, path, payload=None):
        captured.update(method=method, path=path, payload=payload)
        return {"id": 1, "_embedded": {}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.create_time_entry(
        {
            "work_package_id": 1,
            "hours": 2,
            "spent_on": "2026-09-01",
            "activity_id": 3,
            "user_id": 58,
        }
    )

    assert captured["payload"]["_links"]["user"] == {"href": "/api/v3/users/58"}


async def test_client_omits_user_link(monkeypatch):
    client = OpenProjectClient.__new__(OpenProjectClient)
    captured = {}

    async def fake_request(method, path, payload=None):
        captured.update(payload=payload)
        return {"id": 1, "_embedded": {}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.create_time_entry(
        {"work_package_id": 1, "hours": 2, "spent_on": "2026-09-01", "activity_id": 3}
    )

    assert "user" not in captured["payload"].get("_links", {})
