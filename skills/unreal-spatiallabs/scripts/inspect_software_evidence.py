"""Read-only file evidence entry point for an existing ordinary Unreal run."""

from dcc_mcp_core.skill import skill_entry
from dcc_mcp_core.skills_helper import skill_error, skill_success
from spatiallabs_evidence import inspect_software_evidence as _run


@skill_entry
def inspect_software_evidence(project_path, engine_root, run_log_path, capture_path=None, cache_state="unknown"):
    try:
        result = _run(project_path, engine_root, run_log_path, capture_path, cache_state)
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        return skill_error("Software evidence check refused", str(exc))
    return skill_success("Software evidence inspected; no host actions executed", **result)


main = inspect_software_evidence

if __name__ == "__main__":
    from dcc_mcp_core.skills_helper import run_main

    run_main(main)
