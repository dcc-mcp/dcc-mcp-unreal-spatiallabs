"""Read-only SpatialLabs plan_install entry point."""

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success
from spatiallabs_project import plan_install as _run


@skill_entry
def plan_install(project_path, plugin_version, engine_version, source_url, support_evidence=None, license_evidence=None):
    try:
        result = _run(project_path, plugin_version, engine_version, source_url, support_evidence, license_evidence)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return skill_error("SpatialLabs check refused", str(exc))
    return skill_success("SpatialLabs check completed", **result)
