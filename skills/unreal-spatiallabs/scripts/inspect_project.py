"""Read-only SpatialLabs inspect_project entry point."""

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success
from spatiallabs_project import inspect_project as _run


@skill_entry
def inspect_project(project_path, environment=None):
    try:
        result = _run(project_path, environment)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return skill_error("SpatialLabs check refused", str(exc))
    return skill_success("SpatialLabs check completed", **result)
