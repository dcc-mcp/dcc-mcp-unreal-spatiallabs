"""Read-only SpatialLabs analyze_performance entry point."""

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success
from spatiallabs_performance import analyze_performance as _run


@skill_entry
def analyze_performance(baseline, candidate):
    try:
        result = _run(baseline, candidate)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return skill_error("SpatialLabs check refused", str(exc))
    return skill_success("SpatialLabs check completed", **result)
