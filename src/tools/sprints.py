"""Sprint and backlog management tools (OpenProject 17.3+).

Read-only tools over the sprint API. Sprints require the Backlogs module; on
projects without it these tools simply return an empty result. Story points are
intentionally not surfaced: OpenProject 17.5 does not expose them through the
API v3 (no storyPoints attribute or filter), so any total would be meaningless.
"""

import json
from typing import Optional

from src.server import mcp, get_client
from src.utils.formatting import format_error, format_work_package_list


_STATUS_ICONS = {"in_planning": "📋", "active": "🟢", "completed": "✅"}
_VALID_STATUS = set(_STATUS_ICONS)


def _norm_status(value: str) -> str:
    """Normalise a status label to the enum form ('In planning' -> 'in_planning')."""
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _sprint_status(sprint: dict) -> str:
    """Read a sprint's status.

    The API exposes status via ``_links.status`` (title), not a top-level field.
    """
    status = sprint.get("status")
    if not status:
        status = sprint.get("_links", {}).get("status", {}).get("title", "")
    return _norm_status(status) or "unknown"


def _format_sprint(sprint: dict) -> str:
    """Format a single sprint for display."""
    sid = sprint.get("id", "N/A")
    name = sprint.get("name", "Unnamed")
    status = _sprint_status(sprint)
    icon = _STATUS_ICONS.get(status, "❓")
    start = sprint.get("startDate", "—")
    finish = sprint.get("finishDate", "—")
    project = sprint.get("_links", {}).get("definingWorkspace", {}).get("title", "")

    text = f"{icon} **{name}** (ID: {sid})\n"
    text += f"  Status: {status}\n"
    if project:
        text += f"  Project: {project}\n"
    if start != "—" or finish != "—":
        text += f"  Dates: {start} → {finish}\n"
    return text


@mcp.tool
async def list_sprints(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    offset: int = 0,
    page_size: int = 25,
) -> str:
    """List sprints, optionally scoped to a project.

    Requires the Backlogs module (OpenProject 17.3+); projects without it return
    no sprints.

    Args:
        project_id: Optional project ID. If omitted, lists all visible sprints.
        status: Optional status filter: 'in_planning', 'active', or 'completed'.
        offset: Pagination offset (default: 0).
        page_size: Results per page (default: 25, max: 100).

    Returns:
        Formatted list of sprints with status, dates, and project.

    Examples:
        Active sprints in project #5: {"project_id": 5, "status": "active"}
        All sprints: {}
    """
    try:
        if status is not None and _norm_status(status) not in _VALID_STATUS:
            allowed = ", ".join(sorted(_VALID_STATUS))
            return format_error(f"Invalid status '{status}'. Must be one of: {allowed}")
        if page_size < 1 or page_size > 100:
            return format_error("page_size must be between 1 and 100")

        client = get_client()
        result = await client.get_sprints(
            project_id=project_id, offset=offset, page_size=page_size
        )
        sprints = result.get("_embedded", {}).get("elements", [])

        # Status is filtered client-side (the API models it via _links.status).
        if status is not None:
            wanted = _norm_status(status)
            sprints = [s for s in sprints if _sprint_status(s) == wanted]

        total = result.get("total", len(sprints))

        if not sprints:
            scope = f"project #{project_id}" if project_id else "all projects"
            note = f" with status '{status}'" if status else ""
            return f"No sprints found for {scope}{note}."

        scope_label = f"Project #{project_id}" if project_id else "All Projects"
        status_label = f" ({status})" if status else ""
        text = (
            f"🏃 **Sprints — {scope_label}{status_label}** ({len(sprints)} shown)\n\n"
        )
        for sprint in sprints:
            text += _format_sprint(sprint) + "\n"

        if not status and total > offset + len(sprints):
            text += f"📄 Showing {offset + 1}–{offset + len(sprints)} of {total}. "
            text += f"Use offset={offset + page_size} for the next page.\n"

        return text

    except Exception as e:
        return format_error(f"Failed to list sprints: {str(e)}")


@mcp.tool
async def get_sprint(sprint_id: int) -> str:
    """Get details of a single sprint by ID.

    Args:
        sprint_id: The sprint ID.

    Returns:
        Full sprint details including status, dates, and project.
    """
    try:
        client = get_client()
        sprint = await client.get_sprint(sprint_id)

        text = "🏃 **Sprint Details**\n\n"
        text += _format_sprint(sprint)
        text += f"\n**Created**: {sprint.get('createdAt', 'N/A')}\n"
        text += f"**Updated**: {sprint.get('updatedAt', 'N/A')}\n"
        return text

    except Exception as e:
        return format_error(f"Failed to get sprint #{sprint_id}: {str(e)}")


@mcp.tool
async def list_sprint_work_packages(
    sprint_id: int,
    project_id: Optional[int] = None,
    active_only: bool = False,
    page_size: int = 50,
) -> str:
    """List work packages assigned to a specific sprint.

    Args:
        sprint_id: The sprint ID.
        project_id: Optional project ID to narrow the search.
        active_only: If True, only open (non-closed) work packages.
        page_size: Results per page (default: 50, max: 100).

    Returns:
        Formatted list of the sprint's work packages.
    """
    try:
        if page_size < 1 or page_size > 100:
            return format_error("page_size must be between 1 and 100")

        client = get_client()
        filters = [{"sprint": {"operator": "=", "values": [str(sprint_id)]}}]
        filters.append(
            {"status": {"operator": "o" if active_only else "*", "values": []}}
        )

        result = await client.get_work_packages(
            project_id=project_id,
            filters=json.dumps(filters),
            page_size=page_size,
        )
        work_packages = result.get("_embedded", {}).get("elements", [])
        total = result.get("total", len(work_packages))

        if not work_packages:
            return f"No work packages found in sprint #{sprint_id}."

        text = f"📋 **Sprint #{sprint_id} Work Packages**\n\n"
        text += format_work_package_list(work_packages)
        if total > page_size:
            text += f"\n📄 Showing first {page_size} of {total}.\n"
        return text

    except Exception as e:
        return format_error(f"Failed to list sprint work packages: {str(e)}")


@mcp.tool
async def list_backlog_work_packages(
    project_id: int,
    type_ids: Optional[str] = None,
    priority_ids: Optional[str] = None,
    active_only: bool = True,
    page_size: int = 50,
) -> str:
    """List work packages in the product backlog (not assigned to any sprint).

    Args:
        project_id: Project ID to list the backlog for.
        type_ids: Optional comma-separated type IDs (e.g. "1,2").
        priority_ids: Optional comma-separated priority IDs.
        active_only: If True, only open work packages (default: True).
        page_size: Results per page (default: 50, max: 100).

    Returns:
        Formatted backlog list (work packages with no sprint).
    """
    try:
        if page_size < 1 or page_size > 100:
            return format_error("page_size must be between 1 and 100")

        client = get_client()
        filters = [{"sprint": {"operator": "!*", "values": []}}]
        filters.append(
            {"status": {"operator": "o" if active_only else "*", "values": []}}
        )
        if type_ids:
            type_list = [t.strip() for t in type_ids.split(",") if t.strip()]
            if type_list:
                filters.append({"type": {"operator": "=", "values": type_list}})
        if priority_ids:
            prio_list = [p.strip() for p in priority_ids.split(",") if p.strip()]
            if prio_list:
                filters.append({"priority": {"operator": "=", "values": prio_list}})

        result = await client.get_work_packages(
            project_id=project_id,
            filters=json.dumps(filters),
            page_size=page_size,
        )
        work_packages = result.get("_embedded", {}).get("elements", [])
        total = result.get("total", len(work_packages))

        if not work_packages:
            return f"Product backlog for project #{project_id} is empty."

        text = f"📥 **Product Backlog — Project #{project_id}**\n\n"
        text += format_work_package_list(work_packages)
        if total > page_size:
            text += f"\n📄 Showing first {page_size} of {total}.\n"
        return text

    except Exception as e:
        return format_error(f"Failed to list backlog: {str(e)}")
