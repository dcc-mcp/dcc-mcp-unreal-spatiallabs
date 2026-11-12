"""Prepare, but never execute, a bounded UE source-project software validation plan."""

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def prepare_software_plan(project_path, instance_id, steps, max_attempts=1, instance_short=None):
    try:
        from spatiallabs_software import prepare_software_plan as prepare

        result = prepare(project_path, instance_id, steps, max_attempts, instance_short)
    except (ValueError, OSError, TypeError, KeyError, ImportError) as exc:
        return skill_error("Software plan refused", str(exc))
    return skill_success("Software validation plan prepared; no tools were called", **result)
