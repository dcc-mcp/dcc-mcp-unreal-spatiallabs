"""Read-only SpatialLabs validate_archive entry point."""

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success
from spatiallabs_project import validate_archive as _run


@skill_entry
def validate_archive(archive_path, plugin_version, engine_version):
    try:
        result = _run(archive_path, plugin_version, engine_version)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return skill_error("SpatialLabs check refused", str(exc))
    return skill_success("SpatialLabs check completed", **result)
