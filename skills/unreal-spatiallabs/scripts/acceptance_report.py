"""Read-only SpatialLabs acceptance_report entry point."""

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success
from spatiallabs_performance import acceptance_report as _run


@skill_entry
def acceptance_report(evidence):
    try:
        result = _run(evidence)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return skill_error("SpatialLabs check refused", str(exc))
    return skill_success("SpatialLabs check completed", **result)
